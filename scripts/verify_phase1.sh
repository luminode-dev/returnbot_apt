#!/usr/bin/env bash
#
# 워크스페이스 빌드 + Phase 0/1 보류 검증.
#
#   bash ~/returnbot/scripts/verify_phase1.sh
#
# GUI 없이 돌아간다. RViz 육안 확인 대신 tf2_echo 로 프레임별 변환을 실제로 읽어
# 검증하므로 재현 가능하고 CI에도 그대로 쓸 수 있다.
set -uo pipefail

WS="${WS:-$HOME/returnbot/returnbot_ws}"
FAIL=0

log()  { printf '\n== %s\n' "$*"; }
ok()   { printf '  OK   %s\n' "$*"; }
bad()  { printf '  FAIL %s\n' "$*"; FAIL=1; }

# 비대화형 셸은 ~/.bashrc 가 조기 return 하므로 직접 source 한다.
set +u
source /opt/ros/humble/setup.bash
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

cd "${WS}"

# ------------------------------------------------------------------- 빌드
log "colcon build"
if colcon build --symlink-install --event-handlers console_direct- > /tmp/build.log 2>&1; then
  ok "빌드 성공"
else
  bad "빌드 실패"
  tail -30 /tmp/build.log
  exit 1
fi

set +u
source install/setup.bash
set -u

# --------------------------------------------------------------- check_urdf
log "check_urdf (명세 Phase 1 완료 기준)"
XACRO_SRC="src/returnbot_description/urdf/returnbot.urdf.xacro"

if xacro "${XACRO_SRC}" > /tmp/returnbot.urdf 2>/tmp/xacro.err; then
  ok "xacro 렌더 성공"
else
  bad "xacro 렌더 실패"; cat /tmp/xacro.err
fi

if check_urdf /tmp/returnbot.urdf > /tmp/check_urdf.out 2>&1; then
  ok "check_urdf 통과"
  sed 's/^/       /' /tmp/check_urdf.out
else
  bad "check_urdf 실패"; cat /tmp/check_urdf.out
fi

log "인자 오버라이드 재렌더 (Phase 3 매트릭스 전제조건)"
for w in 0.55 0.60 0.65; do
  if xacro "${XACRO_SRC}" body_width:="${w}" wheel_separation:=0.5 > "/tmp/rb_${w}.urdf" 2>/dev/null \
     && check_urdf "/tmp/rb_${w}.urdf" > /dev/null 2>&1; then
    ok "body_width=${w} 렌더 + check_urdf 통과"
  else
    bad "body_width=${w} 실패"
  fi
done

# ------------------------------------------------------------------- 테스트
log "패키지 테스트"
colcon test --event-handlers console_direct- > /tmp/colcon_test.log 2>&1
if colcon test-result > /tmp/test_result.log 2>&1; then
  ok "colcon test 전부 통과 — $(grep -m1 Summary /tmp/colcon_test.log || tail -1 /tmp/test_result.log)"
else
  bad "테스트 실패"
  colcon test-result --verbose 2>&1 | tail -30
fi

# ----------------------------------------------------------------------- TF
# URDF를 -p 로 명령줄에 넘기면 rcl 파라미터 파서가 XML을 못 읽는다.
# launch 파일을 그대로 쓰는 것이 실제 배포 경로이기도 하다.
log "TF 트리 검증 (display.launch.py, GUI 없이)"
ros2 launch returnbot_description display.launch.py \
     gui:=false rviz:=false > /tmp/launch.log 2>&1 &
LAUNCH_PID=$!
cleanup() {
  kill "${LAUNCH_PID}" 2>/dev/null || true
  sleep 1
  pkill -f robot_state_publisher 2>/dev/null || true
  pkill -f joint_state_publisher 2>/dev/null || true
}
trap cleanup EXIT
sleep 12

if grep -q "got segment base_footprint" /tmp/launch.log; then
  ok "robot_state_publisher 기동"
else
  bad "robot_state_publisher 기동 실패"; tail -20 /tmp/launch.log
fi

# 고정 프레임 + 구동륜(continuous, joint_states 필요) 전부 확인
for frame in base_link left_wheel_link right_wheel_link left_caster_link \
             right_caster_link lidar_link imu_link camera_link camera_optical_link; do
  out=$(timeout 8 ros2 run tf2_ros tf2_echo base_footprint "${frame}" 2>/dev/null \
        | grep -m1 -A0 'Translation' || true)
  if [ -n "${out}" ]; then
    ok "TF base_footprint -> ${frame}  ${out#*: }"
  else
    bad "TF base_footprint -> ${frame} 없음"
  fi
done

cleanup
trap - EXIT

# --------------------------------------------------- Phase 0: Gazebo 월드 로드
# Phase 0에서는 SDF가 유효한 XML이라는 것까지만 확인했다. 실제 로드는 여기가 처음이다.
log "Phase 0 월드 로드 (Gazebo Fortress, 헤드리스 서버)"
ENV_PKG="src/returnbot_env"
(cd "${ENV_PKG}" && python3 -m returnbot_env.cli --all --flavor fortress --out /tmp/worlds) \
  > /tmp/gen.log 2>&1 && ok "월드 3종 생성" || { bad "월드 생성 실패"; tail -5 /tmp/gen.log; }

for t in a b c; do
  world="/tmp/worlds/apt_type_${t}.sdf"
  if timeout 90 ign gazebo -s -r --iterations 200 "${world}" > "/tmp/ign_${t}.log" 2>&1; then
    if grep -qiE "error|severe|failed to load" "/tmp/ign_${t}.log"; then
      bad "유형 ${t^^} 로드 중 오류 — /tmp/ign_${t}.log 확인"
      grep -iE "error|severe|failed to load" "/tmp/ign_${t}.log" | head -5
    else
      ok "유형 ${t^^} 월드 200스텝 시뮬 완료"
    fi
  else
    bad "유형 ${t^^} 월드 로드 실패 (타임아웃 또는 비정상 종료)"
    tail -10 "/tmp/ign_${t}.log"
  fi
done

log "요약"
if [ "${FAIL}" -eq 0 ]; then
  echo "전부 통과"
else
  echo "실패 항목 있음 — 위 FAIL 표시 확인"
fi
exit "${FAIL}"
