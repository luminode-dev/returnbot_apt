#!/usr/bin/env bash
#
# 리턴봇 개발 환경 부트스트랩 — WSL2 / Ubuntu 22.04 (Jammy) 전용.
#
# 실행 방법 두 가지:
#
#   1) 일반 사용자로 (sudo 비밀번호를 한 번 묻는다)
#        bash ~/returnbot/scripts/wsl_bootstrap.sh
#
#   2) root로 (Windows에서 비밀번호 없이)
#        wsl -u root bash /home/<user>/returnbot/scripts/wsl_bootstrap.sh
#      이때 rosdep update 와 ~/.bashrc 설정은 RETURNBOT_USER 계정으로 내려가서 실행된다.
#      (rosdep 을 root로 돌리면 캐시 소유권이 망가진다.)
#
# 여러 번 돌려도 안전하다(idempotent).
#
# 환경변수:
#   GAZEBO_FLAVOR=fortress|harmonic|none   기본 fortress
#   INSTALL_EXTRAS=1|0                     기본 1 (Phase 2~3 패키지 함께 설치)
#   RETURNBOT_USER=<이름>                  root 실행 시 대상 사용자 (미지정 시 자동 추정)
#
set -euo pipefail

GAZEBO_FLAVOR="${GAZEBO_FLAVOR:-fortress}"
INSTALL_EXTRAS="${INSTALL_EXTRAS:-1}"
ROS_DISTRO_NAME="humble"

log()  { printf '\n== %s\n' "$*"; }
warn() { printf '경고: %s\n' "$*"; }
die()  { printf '오류: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 사전 점검
log "환경 확인"
[ -r /etc/os-release ] || die "/etc/os-release 를 읽을 수 없다"
. /etc/os-release
if [ "${UBUNTU_CODENAME:-}" != "jammy" ]; then
  die "Ubuntu 22.04(jammy)가 아니다: ${PRETTY_NAME:-unknown}. ROS 2 Humble 바이너리는 jammy 전용이다."
fi
echo "  ${PRETTY_NAME}"

# root면 빈 접두사, 아니면 sudo. 배열로 두는 이유: 빈 문자열을 명령줄에 그대로
# 남기면 뒤따르는 -E 가 명령 이름으로 해석되어 "-E: command not found" 가 난다.
if [ "$(id -u)" -eq 0 ]; then
  SUDO=()
  SUDO_E=(env)
  TARGET_USER="${RETURNBOT_USER:-}"
  if [ -z "${TARGET_USER}" ]; then
    # /home 아래 계정이 정확히 하나면 그 계정으로 본다.
    mapfile -t _homes < <(find /home -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
    [ "${#_homes[@]}" -eq 1 ] || die "대상 사용자를 정할 수 없다. RETURNBOT_USER=<이름> 을 지정할 것."
    TARGET_USER="${_homes[0]}"
  fi
  id "${TARGET_USER}" >/dev/null 2>&1 || die "사용자 ${TARGET_USER} 가 없다"
  echo "  root로 실행 중 · 대상 사용자: ${TARGET_USER}"
else
  SUDO=(sudo)
  SUDO_E=(sudo -E)
  TARGET_USER="$(whoami)"
  echo "  사용자: ${TARGET_USER}"
  log "sudo 자격 확인 (비밀번호를 한 번 묻는다)"
  sudo -v
  ( while true; do sudo -n true 2>/dev/null || exit; sleep 50; kill -0 "$$" 2>/dev/null || exit; done ) &
  trap 'kill %1 2>/dev/null || true' EXIT
fi

TARGET_HOME="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"
[ -d "${TARGET_HOME}" ] || die "홈 디렉터리를 찾을 수 없다: ${TARGET_HOME}"

# 대상 사용자로 명령 실행 (root면 내려가고, 아니면 그냥 실행)
as_user() {
  if [ "$(id -u)" -eq 0 ]; then
    runuser -u "${TARGET_USER}" -- "$@"
  else
    "$@"
  fi
}

export DEBIAN_FRONTEND=noninteractive
apt_install() { "${SUDO_E[@]}" apt-get install -y --no-install-recommends "$@"; }
apt_update()  { "${SUDO_E[@]}" apt-get update; }

# ------------------------------------------------------------------ 기본 도구
log "기본 패키지"
apt_update
apt_install curl gnupg2 ca-certificates lsb-release software-properties-common \
            git build-essential python3-pip python3-pytest python3-yaml

# ------------------------------------------------------------- ROS 2 apt 저장소
log "ROS 2 apt 저장소 등록"
"${SUDO[@]}" add-apt-repository -y universe
if [ ! -s /usr/share/keyrings/ros-archive-keyring.gpg ]; then
  "${SUDO[@]}" curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu ${UBUNTU_CODENAME} main" \
  | "${SUDO[@]}" tee /etc/apt/sources.list.d/ros2.list > /dev/null
apt_update

# ------------------------------------------------------------------ ROS 2 본체
log "ROS 2 ${ROS_DISTRO_NAME} Desktop 설치 (용량이 커서 오래 걸린다)"
apt_install "ros-${ROS_DISTRO_NAME}-desktop" ros-dev-tools \
            python3-colcon-common-extensions python3-rosdep python3-vcstool

log "URDF 검증 / xacro / RViz 조인트 GUI / CycloneDDS"
apt_install liburdfdom-tools \
            "ros-${ROS_DISTRO_NAME}-xacro" \
            "ros-${ROS_DISTRO_NAME}-joint-state-publisher-gui" \
            "ros-${ROS_DISTRO_NAME}-rmw-cyclonedds-cpp"

# ------------------------------------------------------------------- Gazebo
# 명세 §4는 `gz sim`(Garden/Harmonic 계열) 표기지만 Humble의 tier-1 페어링은
# Fortress(`ign gazebo`)다. 실제 apt에 무엇이 있는지 기록하고 설치한다.
log "Gazebo 후보 확인"
apt-cache policy "ros-${ROS_DISTRO_NAME}-ros-gz" || true
apt-cache search "ros-${ROS_DISTRO_NAME}-ros-gz" || true

case "${GAZEBO_FLAVOR}" in
  fortress)
    log "Gazebo Fortress 설치 (ign gazebo)"
    apt_install "ros-${ROS_DISTRO_NAME}-ros-gz"
    ;;
  harmonic)
    log "Gazebo Harmonic 설치 (gz sim) — OSRF 저장소 추가"
    "${SUDO[@]}" curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
      -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable ${UBUNTU_CODENAME} main" \
      | "${SUDO[@]}" tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
    apt_update
    apt_install gz-harmonic "ros-${ROS_DISTRO_NAME}-ros-gzharmonic" \
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
  apt_install "ros-${ROS_DISTRO_NAME}-slam-toolbox" \
              "ros-${ROS_DISTRO_NAME}-navigation2" \
              "ros-${ROS_DISTRO_NAME}-nav2-bringup" \
              "ros-${ROS_DISTRO_NAME}-teleop-twist-keyboard" \
              "ros-${ROS_DISTRO_NAME}-tf2-tools" \
    || warn "일부 패키지 설치 실패 — Phase 2 착수 시 재시도"
fi

# ------------------------------------------------------------------- rosdep
log "rosdep 초기화"
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  "${SUDO[@]}" rosdep init
fi
# root로 돌리면 ~/.ros 소유권이 root가 되어 이후 사용자 실행이 깨진다.
as_user rosdep update

# --------------------------------------------------------------------- 셸 설정
log "${TARGET_HOME}/.bashrc 설정"
as_user bash -c '
set -eu
BASHRC="$HOME/.bashrc"
MARKER="# >>> returnbot ros2 setup >>>"
if grep -qF "$MARKER" "$BASHRC" 2>/dev/null; then
  echo "  이미 설정되어 있음 (건너뜀)"
else
  cat >> "$BASHRC" <<"EOF"

# >>> returnbot ros2 setup >>>
source /opt/ros/humble/setup.bash
# 명세 §4: CycloneDDS 고정
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# WSLg 렌더링이 깨지면 아래 주석을 풀어 소프트웨어 렌더링으로 폴백
# export LIBGL_ALWAYS_SOFTWARE=1
if [ -f "$HOME/returnbot/returnbot_ws/install/setup.bash" ]; then
  source "$HOME/returnbot/returnbot_ws/install/setup.bash"
fi
# <<< returnbot ros2 setup <<<
EOF
  echo "  추가함"
fi
'

# --------------------------------------------------------------------- 검증
log "설치 확인"
set +u
source "/opt/ros/${ROS_DISTRO_NAME}/setup.bash"
set -u

printf '  ROS_DISTRO : %s\n' "${ROS_DISTRO:-미설정}"
for cmd in ros2 colcon xacro check_urdf rviz2 ign gz; do
  printf '  %-11s: %s\n' "${cmd}" "$(command -v "${cmd}" || echo '-')"
done

log "완료"
cat <<EOF
다음 순서:

  1) 새 셸을 열거나:  source ~/.bashrc
  2) 워크스페이스 빌드:
       cd ${TARGET_HOME}/returnbot/returnbot_ws
       rosdep install --from-paths src --ignore-src -r -y
       colcon build --symlink-install
       source install/setup.bash
  3) 보류돼 있던 Phase 1 검증 (docs/phase1_report.md):
       xacro src/returnbot_description/urdf/returnbot.urdf.xacro > /tmp/returnbot.urdf
       check_urdf /tmp/returnbot.urdf
       ros2 launch returnbot_description display.launch.py

  실제로 설치된 Gazebo 계열을 docs/env_reference.md §6 표에 기록할 것.
EOF
