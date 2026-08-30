# WSL2 + ROS 2 Humble 환경 구축

Phase 2 이후에 필요한 실행 환경. **관리자 권한과 재부팅이 필요하므로 사용자가 직접
실행해야 한다.** 각 단계의 확인 명령까지 함께 적었다.

전제: Windows 11 (WSLg가 GUI를 기본 제공 → 별도 X 서버 불필요).

---

## 1. WSL2 + Ubuntu 22.04 설치

**Ubuntu 22.04(Jammy)여야 한다.** ROS 2 Humble의 유일한 지원 대상이다.
24.04를 깔면 Humble 바이너리가 없다.

**관리자 권한 PowerShell**에서:

```powershell
wsl --install -d Ubuntu-22.04
```

→ **재부팅** → Ubuntu 창이 뜨면 사용자 이름·비밀번호 생성.

확인 (일반 PowerShell):
```powershell
wsl -l -v          # Ubuntu-22.04 / Running / 2  가 나와야 한다
```

이미 WSL이 있는데 배포판만 추가하는 경우:
```powershell
wsl --set-default-version 2
wsl --install -d Ubuntu-22.04
```

## 2. 기본 패키지

이하 전부 **Ubuntu(WSL) 셸**에서:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl gnupg lsb-release software-properties-common git python3-pip
lsb_release -a     # Ubuntu 22.04.x LTS 확인
```

## 3. ROS 2 Humble Desktop

```bash
sudo add-apt-repository universe -y
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y ros-humble-desktop ros-dev-tools
```

확인:
```bash
source /opt/ros/humble/setup.bash
ros2 doctor          # 경고는 있을 수 있으나 에러가 없어야 한다
```

## 4. colcon / rosdep

```bash
sudo apt install -y python3-colcon-common-extensions python3-rosdep
sudo rosdep init && rosdep update
```

## 5. Gazebo — **버전 결정이 필요한 지점**

명세 §4는 `gz sim` 표기지만, ROS 2 Humble의 tier-1 페어링은 **Fortress**(`ign gazebo`)다.
시스템 플러그인 이름이 달라서 월드 생성기가 `--flavor` 인자로 둘을 지원하고 있다.

먼저 apt에 무엇이 있는지 **실제로 확인**한다:

```bash
apt-cache policy ros-humble-ros-gz            # Fortress 연동
apt-cache search ros-humble-ros-gz            # Harmonic 변형이 있는지 함께 확인
```

기본안 (Fortress):
```bash
sudo apt install -y ros-humble-ros-gz
ign gazebo --version
```

결정한 뒤 **반드시 `docs/env_reference.md` §6 표에 근거와 함께 기록할 것.**
Fortress로 확정되면 명세 §4의 `gz sim` 표기도 `ign gazebo`로 정정한다.

월드 생성은 그에 맞춰:
```bash
python3 -m returnbot_env.cli --all --flavor fortress   # 또는 harmonic
```

## 6. CycloneDDS 고정 (명세 §4)

```bash
sudo apt install -y ros-humble-rmw-cyclonedds-cpp
echo 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' >> ~/.bashrc
```

확인:
```bash
source ~/.bashrc && echo $RMW_IMPLEMENTATION
```

## 7. 워크스페이스 배치 — `/mnt/c` 를 쓰지 말 것

WSL에서 `/mnt/c/...` 는 파일 I/O가 느리고 퍼미션·심볼릭링크 문제가 있어 colcon 빌드에
적합하지 않다. 게다가 이 저장소 경로에는 한글(`리턴봇`)이 들어 있다.

**WSL 홈에 따로 clone한다:**

```bash
cd ~
git clone https://github.com/luminode-dev/returnbot_apt.git returnbot
cd returnbot/returnbot_ws
```

편집은 Windows/VSCode에서 하고, 동기화는 origin을 경유한다
(또는 VSCode의 WSL 원격 확장으로 WSL 쪽을 직접 연다).

## 8. 빌드

```bash
cd ~/returnbot/returnbot_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

## 9. 보류 중인 Phase 1 검증 해소

환경이 서면 **가장 먼저** 이것부터 확인한다 (`docs/phase1_report.md`의 "보류" 항목):

```bash
# check_urdf
xacro src/returnbot_description/urdf/returnbot.urdf.xacro > /tmp/returnbot.urdf
check_urdf /tmp/returnbot.urdf

# 인자 반영 재확인
xacro src/returnbot_description/urdf/returnbot.urdf.xacro \
      body_width:=0.65 wheel_separation:=0.5 > /tmp/wide.urdf
check_urdf /tmp/wide.urdf

# RViz TF 육안 확인
ros2 launch returnbot_description display.launch.py
```

## 10. Phase 0 월드 로드 확인

SDF가 유효한 XML이라는 것까지만 확인된 상태다. 실제 로드는 여기서 처음 검증한다:

```bash
cd ~/returnbot/returnbot_ws/src/returnbot_env
python3 -m returnbot_env.cli --all --flavor fortress
ign gazebo worlds/apt_type_a.sdf      # Harmonic이면 gz sim
```

---

## 알려진 함정

| 증상 | 원인 / 대처 |
|---|---|
| `ros2` 명령 없음 | 셸마다 `source /opt/ros/humble/setup.bash` 필요. `~/.bashrc`에 추가 |
| RViz/Gazebo 창이 안 뜸 | WSLg 미동작. `wsl --update` 후 `wsl --shutdown` |
| GPU 렌더링 실패 | `export LIBGL_ALWAYS_SOFTWARE=1` 로 소프트웨어 렌더링 폴백 |
| colcon 빌드가 매우 느림 | 워크스페이스가 `/mnt/c` 에 있는 경우. §7대로 WSL 홈으로 옮길 것 |
| 스크립트 실행 시 `bad interpreter` | CRLF 줄바꿈. 저장소 루트 `.gitattributes`가 `eol=lf`로 막고 있으나, WSL 밖에서 편집기가 강제 변환했는지 확인 |
| `rosdep install` 에서 `TODO` 라이선스 경고 | package.xml 라이선스가 미정 상태다. 저장소 LICENSE 확정 시 함께 갱신 |
