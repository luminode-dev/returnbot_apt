# 리턴봇 (ReturnBot)

한국 아파트 공용부를 주행하며 세대 앞 분리수거함을 회수·교환하는 자율주행 로봇의
**시뮬레이션 검증 프로젝트**.

하드웨어 조립 전에 차체 치수(특히 편복도 1.2 m를 통과할 수 있는 폭)와 Nav2 파라미터를
시뮬레이션으로 확정하는 것이 목적이다. 작업 명세는 [`returnbot-sim-spec.md`](returnbot-sim-spec.md).

## 현재 상태

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | 환경 기준 정리 + 파라메트릭 월드 생성기 | **완료 · Gazebo 로드 검증됨** — [리포트](docs/phase0_report.md) |
| 1 | URDF 모델링 | **완료 · check_urdf + TF 검증됨** — [리포트](docs/phase1_report.md) |
| 2 | Gazebo 주행 검증 + SLAM | **완료** — [리포트](docs/phase2_report.md) |
| 3 | Nav2 자율주행 + 차체폭 매트릭스 | 미착수 |
| 4 | Isaac Sim 트윈 + AprilTag 도킹 | 미착수 |

**환경**: WSL2 + Ubuntu 22.04.5 · ROS 2 Humble · Gazebo Fortress (Sim 6.18.0) · CycloneDDS.
`scripts/wsl_bootstrap.sh` 한 번으로 재현된다.

```
$ bash scripts/verify_phase1.sh
colcon build                                   OK
check_urdf                                     OK
body_width 0.55/0.60/0.65 재렌더 + check_urdf   OK
colcon test              107 tests, 0 errors, 0 failures
TF 9개 프레임 전부 확인                          OK
Gazebo 월드 3유형 200스텝 시뮬                   OK
```

## 저장소 구조

```
docs/
├── env_reference.md      # 복도 폭 등 환경 치수의 법적 근거 (확정/참고/TODO)
├── phase0_report.md
├── phase1_report.md
└── phase0/               # 생성된 3유형 평면도 (SVG)

returnbot_ws/src/
├── returnbot_description/  # URDF(xacro) — Phase 1 ✅
├── returnbot_env/          # 아파트 파라메트릭 월드 생성기 — Phase 0 ✅
├── returnbot_sim/          # Gazebo 플러그인·시뮬 launch — Phase 2 ✅
├── returnbot_navigation/   # 기준 맵 3종 ✅ / Nav2 config·BT — Phase 3
├── returnbot_bringup/      # 공용 launch·파라미터 — Phase 3
└── returnbot_docking/      # AprilTag 도킹 — Phase 4
```

## 실행

### WSL / ROS 2 환경

```bash
cd ~/returnbot/returnbot_ws && source install/setup.bash

ros2 launch returnbot_description display.launch.py                    # RViz로 로봇 확인

# Gazebo 시뮬 (유형 A 편복도)
ros2 launch returnbot_sim gazebo.launch.py apt_type:=A
ros2 launch returnbot_sim mapping.launch.py apt_type:=B              # + slam_toolbox
ros2 launch returnbot_sim gazebo.launch.py apt_type:=A clutter:=true # 적치물 시나리오
ros2 run returnbot_sim drive_mapping_run.py --ros-args -p apt_type:=A

bash ~/returnbot/scripts/verify_phase1.sh    # Phase 0/1 전체 검증
bash ~/returnbot/scripts/run_mapping.sh all  # 기준 맵 3종 재생성
```

### ROS 없이 (Windows에서도)

Python 3만 있으면 된다 (`pip install pyyaml pytest xacro`).

```bash
# 아파트 월드 3유형 생성 + 평면도
cd returnbot_ws/src/returnbot_env
python -m returnbot_env.cli --all --svg-dir ../../../docs/phase0
python -m returnbot_env.cli --list-todo     # 근거 미확보 치수 목록
python -m pytest tests -q                   # 55 passed

# URDF 검증 (순기구학으로 접지·하중비·관성 확인)
cd ../returnbot_description
python -m pytest tests -q                   # 51 passed
```

생성된 평면도는 [`docs/phase0/`](docs/phase0/)에 있다. VSCode에서 SVG를 바로 열어볼 수 있다.

## 설계 원칙

- **치수는 코드에 없다.** 전부 yaml에 `{value, confidence, source}` 형태로 근거와 함께
  둔다 (명세 §7). 근거를 확보하지 못한 값은 그럴듯한 숫자로 메우지 않고
  `TODO(확인)`으로 추적한다
- **월드는 하나의 중립 IR에서 생성한다.** SDF·USD·평면도 백엔드가 같은 `ir.Scene`을
  소비하므로 Isaac Sim용 USD를 나중에 붙여도 지오메트리가 갈라지지 않는다
- **description 패키지에 시뮬 전용 요소를 넣지 않는다.** 실기(Pi 5 + ESP32)에
  그대로 이식하고, 시뮬 분기는 launch 인자로만 한다. Gazebo 태그는 `returnbot_sim` 에만 있다

## 환경 구축

ROS 2 Humble은 **Ubuntu 22.04(Jammy)** 전용이다. 개발 PC가 Windows이므로 WSL2에
Ubuntu 22.04를 올린다. Windows 11의 WSLg가 GUI를 제공하므로 별도 X 서버가 필요 없다
(RViz2가 OpenGL 4.2로 기동하는 것까지 확인).

```powershell
wsl --install -d Ubuntu-22.04     # 관리자 PowerShell, 이후 재부팅
```

```bash
git clone https://github.com/luminode-dev/returnbot_apt.git ~/returnbot
bash ~/returnbot/scripts/wsl_bootstrap.sh
```

`/mnt/c` 에서 colcon 빌드하지 말 것 — 느리고 퍼미션 문제가 있다. 상세 절차와 함정은
[`docs/wsl_setup.md`](docs/wsl_setup.md) 참조.

## 근거 문서

복도 유효폭 1.2 m / 1.8 m의 출처는 **「건축물의 피난·방화구조 등의 기준에 관한 규칙」
제15조의2 제1항**이다 (명세 §2.1이 적은 「주택건설기준 등에 관한 규정」이 아니다).
승강기 출입문·활동공간 기준은 「장애인·노인·임산부 등의 편의증진 보장에 관한 법률
시행규칙」 별표 1. 상세는 [`docs/env_reference.md`](docs/env_reference.md).
