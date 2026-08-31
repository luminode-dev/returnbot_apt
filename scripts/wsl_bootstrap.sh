#!/usr/bin/env bash
#
# 리턴봇 개발 환경 부트스트랩 — WSL2 / Ubuntu 22.04 (Jammy) 전용.
#
#   bash ~/returnbot/scripts/wsl_bootstrap.sh
#
# 시작할 때 sudo 비밀번호를 한 번 묻고, 이후 apt 작업 동안 자격을 갱신한다.
# 여러 번 돌려도 안전하다(idempotent).
#
# 환경변수:
#   GAZEBO_FLAVOR=fortress|harmonic|none   기본 fortress
#   INSTALL_EXTRAS=1|0                     기본 1 (Phase 2~3 패키지 함께 설치)
#
set -euo pipefail

GAZEBO_FLAVOR="${GAZEBO_FLAVOR:-fortress}"
INSTALL_EXTRAS="${INSTALL_EXTRAS:-1}"
ROS_DISTRO_NAME="humble"

log()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m경고: %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m오류: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 사전 점검
log "환경 확인"
[ -r /etc/os-release ] || die "/etc/os-release 를 읽을 수 없다"
. /etc/os-release
if [ "${UBUNTU_CODENAME:-}" != "jammy" ]; then
  die "Ubuntu 22.04(jammy)가 아니다: ${PRETTY_NAME:-unknown}
     ROS 2 Humble 바이너리는 jammy 전용이다. 배포판을 다시 확인할 것."
fi
echo "  ${PRETTY_NAME}"
echo "  사용자: $(whoami)   홈: ${HOME}"
[ "$(id -u)" -ne 0 ] || die "root로 실행하지 말 것. 일반 사용자로 실행하면 내부에서 sudo를 쓴다."

# sudo 자격을 미리 받고, 긴 apt 작업 동안 백그라운드로 갱신한다.
log "sudo 자격 확인 (비밀번호를 한 번 묻는다)"
sudo -v
( while true; do sudo -n true 2>/dev/null || exit; sleep 50; kill -0 "$$" 2>/dev/null || exit; done ) &
SUDO_KEEPALIVE=$!
trap 'kill "${SUDO_KEEPALIVE}" 2>/dev/null || true' EXIT

export DEBIAN_FRONTEND=noninteractive
APT_INSTALL=(sudo -E apt-get install -y --no-install-recommends)

# ------------------------------------------------------------------ 기본 도구
log "기본 패키지"
sudo -E apt-get update
"${APT_INSTALL[@]}" \
  curl gnupg2 ca-certificates lsb-release software-properties-common \
  git build-essential python3-pip python3-pytest python3-yaml

# ------------------------------------------------------------- ROS 2 apt 저장소
log "ROS 2 apt 저장소 등록"
sudo add-apt-repository -y universe
if [ ! -s /usr/share/keyrings/ros-archive-keyring.gpg ]; then
  sudo curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu ${UBUNTU_CODENAME} main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo -E apt-get update

# ------------------------------------------------------------------ ROS 2 본체
log "ROS 2 ${ROS_DISTRO_NAME} Desktop 설치 (용량이 커서 오래 걸린다)"
"${APT_INSTALL[@]}" \
  "ros-${ROS_DISTRO_NAME}-desktop" \
  ros-dev-tools \
  python3-colcon-common-extensions \
  python3-rosdep \
  python3-vcstool

log "패키지 추가 — URDF 검증 / xacro / RViz 조인트 GUI"
"${APT_INSTALL[@]}" \
  liburdfdom-tools \
  "ros-${ROS_DISTRO_NAME}-xacro" \
  "ros-${ROS_DISTRO_NAME}-joint-state-publisher-gui" \
  "ros-${ROS_DISTRO_NAME}-rmw-cyclonedds-cpp"

# ------------------------------------------------------------------- Gazebo
# 명세 §4는 `gz sim`(Garden/Harmonic 계열) 표기지만 Humble의 tier-1 페어링은
# Fortress(`ign gazebo`)다. 실제 apt에 무엇이 있는지 확인한 뒤 설치한다.
log "Gazebo 후보 확인"
echo "--- ros-${ROS_DISTRO_NAME}-ros-gz (Fortress 연동) ---"
apt-cache policy "ros-${ROS_DISTRO_NAME}-ros-gz" || true
echo "--- ros-gz 계열 검색 결과 ---"
apt-cache search "ros-${ROS_DISTRO_NAME}-ros-gz" || true

case "${GAZEBO_FLAVOR}" in
  fortress)
    log "Gazebo Fortress 설치 (ign gazebo)"
    "${APT_INSTALL[@]}" "ros-${ROS_DISTRO_NAME}-ros-gz"
    ;;
  harmonic)
    log "Gazebo Harmonic 설치 (gz sim) — OSRF 저장소 추가"
    sudo curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
      -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable ${UBUNTU_CODENAME} main" \
      | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
    sudo -E apt-get update
    "${APT_INSTALL[@]}" gz-harmonic "ros-${ROS_DISTRO_NAME}-ros-gzharmonic" \
      || die "Harmonic 연동 패키지를 찾지 못했다. GAZEBO_FLAVOR=fortress 로 다시 실행할 것."
    ;;
  none)
    warn "Gazebo 설치를 건너뛴다"
    ;;
  *)
    die "GAZEBO_FLAVOR 값이 잘못됐다: ${GAZEBO_FLAVOR} (fortress|harmonic|none)"
    ;;
esac

# ------------------------------------------------------- Phase 2~3 선행 패키지
if [ "${INSTALL_EXTRAS}" = "1" ]; then
  log "Phase 2~3 패키지 (slam_toolbox / Nav2 / 텔레옵)"
  # 지금 함께 깔아두면 나중에 sudo 비밀번호를 다시 묻지 않아도 된다.
  "${APT_INSTALL[@]}" \
    "ros-${ROS_DISTRO_NAME}-slam-toolbox" \
    "ros-${ROS_DISTRO_NAME}-navigation2" \
    "ros-${ROS_DISTRO_NAME}-nav2-bringup" \
    "ros-${ROS_DISTRO_NAME}-teleop-twist-keyboard" \
    "ros-${ROS_DISTRO_NAME}-tf2-tools" || warn "일부 패키지 설치 실패 — Phase 2 착수 시 재시도"
fi

# ------------------------------------------------------------------- rosdep
log "rosdep 초기화"
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  sudo rosdep init
fi
rosdep update   # root로 하면 안 된다

# --------------------------------------------------------------------- 셸 설정
log "~/.bashrc 설정"
BASHRC="${HOME}/.bashrc"
MARKER="# >>> returnbot ros2 setup >>>"
if ! grep -qF "${MARKER}" "${BASHRC}" 2>/dev/null; then
  cat >> "${BASHRC}" <<'EOF'

# >>> returnbot ros2 setup >>>
source /opt/ros/humble/setup.bash
# 명세 §4: CycloneDDS 고정
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# WSLg에서 렌더링이 깨지면 아래 주석을 풀어 소프트웨어 렌더링으로 폴백
# export LIBGL_ALWAYS_SOFTWARE=1
if [ -f "$HOME/returnbot/returnbot_ws/install/setup.bash" ]; then
  source "$HOME/returnbot/returnbot_ws/install/setup.bash"
fi
# <<< returnbot ros2 setup <<<
EOF
  echo "  추가함"
else
  echo "  이미 설정되어 있음 (건너뜀)"
fi

# --------------------------------------------------------------------- 검증
log "설치 확인"
set +u
source "/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

printf '  ROS_DISTRO        : %s\n' "${ROS_DISTRO:-미설정}"
printf '  RMW_IMPLEMENTATION: %s\n' "${RMW_IMPLEMENTATION}"
printf '  ros2              : %s\n' "$(command -v ros2 || echo MISSING)"
printf '  colcon            : %s\n' "$(command -v colcon || echo MISSING)"
printf '  xacro             : %s\n' "$(command -v xacro || echo MISSING)"
printf '  check_urdf        : %s\n' "$(command -v check_urdf || echo MISSING)"
printf '  ign gazebo        : %s\n' "$(command -v ign || echo -)"
printf '  gz sim            : %s\n' "$(command -v gz || echo -)"

log "완료"
cat <<'EOF'
다음 순서:

  1) 새 셸을 열거나:  source ~/.bashrc
  2) 워크스페이스 빌드:
       cd ~/returnbot/returnbot_ws
       rosdep install --from-paths src --ignore-src -r -y
       colcon build --symlink-install
       source install/setup.bash
  3) 보류돼 있던 Phase 1 검증 (docs/phase1_report.md):
       xacro src/returnbot_description/urdf/returnbot.urdf.xacro > /tmp/returnbot.urdf
       check_urdf /tmp/returnbot.urdf
       ros2 launch returnbot_description display.launch.py

  실제로 설치된 Gazebo 계열을 docs/env_reference.md §6 표에 기록할 것.
EOF
