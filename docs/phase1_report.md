# Phase 1 리포트 — URDF 모델링

명세 §6 Phase 1. 작성일 2026-08-30.

## 완료 기준 대비

명세: **"check_urdf 통과, TF 정상, 바퀴간격·차체폭 인자 노출"**

| 항목 | 상태 | 비고 |
|---|---|---|
| xacro: base_link, 구동륜 2(continuous), 캐스터 2, lidar/imu/camera_link | 완료 | |
| 관성값 xacro 매크로 계산 (60 kg, 60:40 배분) | 완료 | 상수 하드코딩 없음 |
| 치수 전부 인자화 | 완료 | 7개 인자 노출 + yaml 원본 |
| robot_state_publisher + RViz2 launch | 완료 | 실행 확인은 ROS 환경 필요 |
| `check_urdf` 통과 | **동등 검증 완료, 명령 실행은 보류** | 아래 참조 |
| TF 정상 | **동등 검증 완료, RViz 확인은 보류** | 아래 참조 |
| 바퀴간격·차체폭 인자 노출 | 완료 | 3값씩 스윕 검증 |

## 산출물

```
returnbot_ws/src/returnbot_description/
├── config/robot_dimensions.yaml   # 치수 원본 {value, confidence, source}
├── urdf/
│   ├── returnbot.urdf.xacro       # 최상위
│   ├── robot_params.xacro         # 인자·속성·파생치수 (무게배분 역산 포함)
│   ├── inertial_macros.xacro      # box/cylinder/sphere 관성
│   ├── materials.xacro
│   ├── base.xacro / wheels.xacro / casters.xacro / sensors.xacro
├── launch/display.launch.py       # yaml → xacro 인자 → RSP + JSP GUI + RViz2
├── rviz/returnbot.rviz
└── tests/                         # ROS 없이 도는 URDF 검증
```

## 결과 형상 (기본 인자)

| 항목 | 값 |
|---|---|
| 총질량 | 60.000 kg (명세 §3과 정확히 일치) |
| 질량중심 | x = −0.160 m, y = 0.000 m, z = 0.206 m |
| **캐스터 하중비** | **0.400** (명세 §3 구동축:캐스터 = 60:40) |
| 구동륜 | Ø200 × 50 mm, x = 0, y = ±0.225 m, z = 0.100 m |
| 캐스터 | Ø100 mm, x = −0.400 m, y = ±0.200 m, z = 0.050 m |
| 차체 박스 | 700(D) × 550(W) × 360(H) mm, 바닥이격 40 mm, 전고 400 mm |
| LiDAR | z = 0.420 m (차체 최상면 위) |
| 카메라 | x = 0.197 m, z = 0.300 m |

링크 질량: 차체 53.10 / 구동륜 2.50×2 / 캐스터 0.80×2 / LiDAR 0.20 / IMU 0.02 / 카메라 0.08

## 설계 판단

### 무게배분을 상수가 아니라 역산으로 구현
지지점이 구동축(x=0)과 캐스터축(x=−wheelbase) 두 곳이므로 캐스터 하중비는 전체
질량중심의 x 위치로만 결정된다. 목표 비율에서 차체 질량중심 x를 풀어 쓰기 때문에
질량·배분비·치수 중 무엇을 바꿔도 60:40이 유지된다. Phase 3 매트릭스 실험이 차체폭을
바꿔가며 도는데, 그때마다 무게배분이 조용히 틀어지면 결과를 신뢰할 수 없다.

### base_link를 구동축 중심에 배치
차동구동의 순간회전중심이 구동축 위에 있어 odom·cmd_vel 계산과 명세 Phase 3의
rotate-in-place 정책이 단순해진다.

### description 패키지에 시뮬 요소를 넣지 않음
명세 §7 "실기/시뮬 분기는 launch 인자로만". Gazebo 센서 플러그인은 Phase 2에서
별도 파일로 붙인다.

## 검증

```
$ python -m pytest tests -q
51 passed
```

`check_urdf`가 하는 검사(단일 루트·순환 없음·트리 무결성)를 순수 파이썬 순기구학으로
수행했다. ROS 없이 돌기 때문에 WSL 구축 전에 설계 오류를 잡을 수 있고, 구축 후에는
`check_urdf`로 이중 검증한다.

`check_urdf`보다 더 본 것:
- **구동륜·캐스터가 모두 지면에 닿는지** — 하나라도 뜨면 Gazebo에서 로봇이 기운다
- **캐스터 하중비 0.400** — wheelbase 0.35/0.40/0.50 세 값에서 모두
- 관성이 치수 공식과 일치하고 주모멘트 삼각부등식을 만족하는지 (위반하면 솔버 발산)
- 카메라 광학 프레임의 REP-103 정합 (apriltag_ros 전제조건)
- `body_width` 550/600/650, `wheel_separation` 400/450/500 인자 반영 —
  **비주얼과 콜리전 양쪽** 확인
- xacro 기본값이 `robot_dimensions.yaml`과 동기화되어 있는지 (23개 치수)

### 검증 중 잡은 결함 1건
**무게배분이 60:40이 아니라 62.8:37.2였다.** 차체 질량중심 계산에서 바퀴·캐스터만
고려하고 전방 카메라(0.08 kg, 차체 중심에서 +0.365 m)를 빠뜨렸다. 명세 §3의 핵심
사양이라 눈에 잘 띄지 않는 채로 Phase 2~3 전체에 영향을 줄 수 있었다.

## 알려진 한계

- **캐스터가 스위블이 아닌 구형 근사다.** 스위블 축 회전 저항을 모사하지 못하므로
  명세 §1 검증항목 3 "피벗턴 시 캐스터 저항에 의한 경로 밀림"이 **현재 모델로는
  재현되지 않는다.** 등가 마찰계수로 크기만 흉내낸다. 명세 §8 리스크대로 Phase 4에서
  조인트 기반 상세화 검토
- **`check_urdf` / RViz 실행 미확인.** ROS 2 환경이 없어 명령 자체는 돌리지 못했다.
  WSL 구축 직후 최우선으로 확인할 것
- **launch 파일 실행 미확인.** 문법 오류는 없으나 `Command` 치환과
  `ament_index_python` 경로 해석은 실제 실행에서만 확인된다
- 메시 없음 (전부 기본 도형). 명세 §2.3의 Phase 0~3 원칙에 맞다

## TODO(확인) — 명세에도 없어 임의 설정한 값

| 항목 | 현재값 | 왜 중요한가 |
|---|---|---|
| `body.ground_clearance` | 40 mm | 문턱 15~20 mm 통과와 직결 |
| `chassis.wheelbase` | 400 mm | 피벗턴 시 캐스터 저항의 모멘트암 |
| `caster.separation` | 400 mm | 좌우 캐스터 간격 |
| `drive.wheel_mass` | 2.5 kg | 허브모터+솔리드타이어 실측 필요 |
| `caster.mass` | 0.8 kg | |
| `friction.*` | mu 1.0 / 0.05 | 명세 §8 — 시뮬-실기 갭이 큰 튜닝 시작점 |
| 센서 외형 치수 | — | LD19/BNO085 데이터시트 확인 필요 |
| `sensors.camera.mount_height` | 300 mm | 수거함 AprilTag 높이에 맞춰 결정 (Phase 4) |

## 다음 단계

1. WSL2 + Ubuntu 22.04 + ROS 2 Humble 구축
2. `check_urdf` / RViz TF 확인으로 이 리포트의 "보류" 항목 해소
3. Gazebo 계열(Fortress vs Harmonic) 확정 → `docs/env_reference.md` §6 기록
4. Phase 2: Gazebo 플러그인 부착, Phase 0 월드에서 텔레옵 주행 + slam_toolbox 맵핑
