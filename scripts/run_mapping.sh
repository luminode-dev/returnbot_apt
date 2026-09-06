#!/usr/bin/env bash
#
# 유형별 맵핑 1회 실행 → 맵 저장 (명세 §6 Phase 2).
#
#   bash scripts/run_mapping.sh A
#   bash scripts/run_mapping.sh all
#   GUI=1 bash scripts/run_mapping.sh A      # Gazebo GUI + RViz 를 띄운 채로
#
# 맵은 returnbot_navigation/maps/ 에 저장한다 (유형별 3개, 명세 Phase 2 완료 기준).
set -uo pipefail

WS="${WS:-$HOME/returnbot/returnbot_ws}"
MAP_DIR="${MAP_DIR:-$WS/src/returnbot_navigation/maps}"
GUI="${GUI:-0}"
DRIVE_TIMEOUT="${DRIVE_TIMEOUT:-600}"

log() { printf '\n== %s\n' "$*"; }

set +u
source /opt/ros/humble/setup.bash
source "${WS}/install/setup.bash"
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

mkdir -p "${MAP_DIR}"

kill_all() {
  pkill -f "ign gazebo" 2>/dev/null
  pkill -f parameter_bridge 2>/dev/null
  pkill -f robot_state_publisher 2>/dev/null
  pkill -f slam_toolbox 2>/dev/null
  pkill -f rviz2 2>/dev/null
  pkill -f "ruby /usr/bin/ign" 2>/dev/null
  sleep 3
}

map_one() {
  local t="$1"
  local lower
  lower=$(echo "$t" | tr 'A-Z' 'a-z')

  log "유형 ${t} 맵핑 시작"
  kill_all

  local headless="true" rviz="false"
  if [ "${GUI}" = "1" ]; then headless="false"; rviz="true"; fi

  ros2 launch returnbot_sim mapping.launch.py \
       apt_type:="${t}" headless:="${headless}" rviz:="${rviz}" \
       > "/tmp/mapping_${lower}.log" 2>&1 &
  local LP=$!

  # Gazebo + slam_toolbox 가 자리를 잡을 때까지 기다린다.
  # GUI 를 띄우면 소프트웨어 렌더링이라 기동이 더 느리다.
  local warmup=25
  [ "${GUI}" = "1" ] && warmup=45
  sleep "${warmup}"

  if ! ros2 topic list 2>/dev/null | grep -q '^/scan$'; then
    echo "  FAIL: /scan 이 없다 — /tmp/mapping_${lower}.log 확인"
    kill "${LP}" 2>/dev/null; kill_all
    return 1
  fi

  log "유형 ${t} 자동 주행"
  timeout "${DRIVE_TIMEOUT}" ros2 run returnbot_sim drive_mapping_run.py --ros-args \
      -p apt_type:="${t}" -p use_sim_time:=true 2>&1 | grep -E "INFO|WARN|ERROR" | sed 's/^/  /'

  log "유형 ${t} 맵 저장"
  sleep 3
  if ros2 run nav2_map_server map_saver_cli -f "${MAP_DIR}/apt_type_${lower}" \
        --ros-args -p use_sim_time:=true > "/tmp/save_${lower}.log" 2>&1; then
    echo "  저장됨: ${MAP_DIR}/apt_type_${lower}.{pgm,yaml}"
    python3 - "$MAP_DIR/apt_type_${lower}.pgm" <<'PY'
import sys
path = sys.argv[1]
with open(path, 'rb') as fh:
    magic = fh.readline().strip()
    line = fh.readline()
    while line.startswith(b'#'):
        line = fh.readline()
    w, h = (int(v) for v in line.split())
    fh.readline()
    data = fh.read()
# map_saver 규약: 0 = 점유, 254 = 자유, 205 = 미지
occupied = sum(1 for b in data if b < 100)
free = sum(1 for b in data if b > 250)
unknown = len(data) - occupied - free
print(f"  맵 {w}x{h}  점유={occupied}  자유={free}  미지={unknown}")
PY
  else
    echo "  FAIL: 맵 저장 실패"
    tail -5 "/tmp/save_${lower}.log"
    kill "${LP}" 2>/dev/null; kill_all
    return 1
  fi

  kill "${LP}" 2>/dev/null
  kill_all
  return 0
}

TARGET="${1:-A}"
FAIL=0
if [ "${TARGET}" = "all" ]; then
  for t in A B C; do map_one "$t" || FAIL=1; done
else
  map_one "$(echo "${TARGET}" | tr 'a-z' 'A-Z')" || FAIL=1
fi

log "요약"
ls -la "${MAP_DIR}" 2>/dev/null | grep -E "\.pgm|\.yaml" || echo "  (맵 없음)"
exit "${FAIL}"
