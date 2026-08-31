#!/usr/bin/env bash
#
# 워크스페이스 빌드 + Phase 1 보류 검증 (docs/phase1_report.md).
#
#   bash ~/returnbot/scripts/verify_phase1.sh
#
# GUI 없이 돌아간다. RViz 대신 tf2_echo / view_frames 로 TF 트리를 실제로 검증한다.
# (RViz 육안 확인보다 재현 가능하고, CI에도 그대로 쓸 수 있다.)
set -uo pipefail

WS="${WS:-$HOME/returnbot/returnbot_ws}"
FAIL=0

log()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32mOK\033[0m   %s\n' "$*"; }
bad()  { printf '  \033[1;31mFAIL\033[0m %s\n' "$*"; FAIL=1; }

# ROS 환경. 비대화형 셸은 ~/.bashrc 가 조기 return 하므로 직접 source 한다.
set +u
source /opt/ros/humble/setup.bash
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

cd "${WS}"

# ------------------------------------------------------------------- 빌드
log "rosdep"
rosdep install --from-paths src --ignore-src -r -y || bad "rosdep install 실패"

log "colcon build"
if colcon build --symlink-install --event-handlers console_direct-; then
  ok "빌드 성공"
else
  bad "빌드 실패"
  exit 1
fi

set +u
source install/setup.bash
set -u

# --------------------------------------------------------------- check_urdf
log "check_urdf (명세 Phase 1 완료 기준)"
XACRO_SRC="src/returnbot_description/urdf/returnbot.urdf.xacro"

xacro "${XACRO_SRC}" > /tmp/returnbot.urdf 2>/tmp/xacro.err \
  && ok "xacro 렌더 성공" || { bad "xacro 렌더 실패"; cat /tmp/xacro.err; }

if check_urdf /tmp/returnbot.urdf > /tmp/check_urdf.out 2>&1; then
  ok "check_urdf 통과"
  sed 's/^/       /' /tmp/check_urdf.out
else
  bad "check_urdf 실패"
  cat /tmp/check_urdf.out
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
if colcon test --event-handlers console_direct- > /tmp/colcon_test.log 2>&1; then
  ok "colcon test 실행 완료"
else
  bad "colcon test 실행 중 오류"
fi
colcon test-result --verbose 2>&1 | tail -25

# ----------------------------------------------------------------------- TF
log "TF 트리 검증 (robot_state_publisher 기동)"
ros2 run robot_state_publisher robot_state_publisher \
  --ros-args -p "robot_description:=$(cat /tmp/returnbot.urdf)" \
  > /tmp/rsp.log 2>&1 &
RSP_PID=$!
# 구동륜은 continuous 라 joint_state 가 있어야 TF가 완성된다.
ros2 run joint_state_publisher joint_state_publisher > /tmp/jsp.log 2>&1 &
JSP_PID=$!
trap 'kill ${RSP_PID} ${JSP_PID} 2>/dev/null || true' EXIT
sleep 6

echo "  --- 발행 중인 프레임 ---"
ros2 run tf2_ros tf2_echo base_footprint lidar_link --once 2>/dev/null | head -6 \
  || echo "  (tf2_echo --once 미지원 — 아래 개별 확인으로 대체)"

for frame in base_link left_wheel_link right_wheel_link left_caster_link \
             right_caster_link lidar_link imu_link camera_link camera_optical_link; do
  if timeout 5 ros2 run tf2_ros tf2_echo base_footprint "${frame}" 2>/dev/null | grep -q 'Translation'; then
    ok "TF base_footprint -> ${frame}"
  else
    bad "TF base_footprint -> ${frame} 없음"
  fi
done

log "요약"
if [ "${FAIL}" -eq 0 ]; then
  printf '\033[1;32m전부 통과\033[0m\n'
else
  printf '\033[1;31m실패 항목 있음 — 위 FAIL 표시 확인\033[0m\n'
fi
exit "${FAIL}"
