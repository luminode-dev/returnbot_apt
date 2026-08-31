# returnbot_description

리턴봇 URDF(xacro) 모델 (명세 §6 Phase 1).

시뮬 전용 요소(Gazebo 플러그인·센서 발행)는 **넣지 않는다**. 실기와 그대로 공용하는
순수 기술 모델이고, 시뮬 분기는 launch 인자로만 한다 (명세 §7).

## 프레임

```
base_footprint            바닥 투영점 (구동축 중심 바로 아래)
└── base_link             구동축 높이 = wheel_radius. 차동구동 순간회전중심
    ├── left/right_wheel_link    continuous, 회전축 = 차량 y
    ├── left/right_caster_link   fixed (구형 근사 — 아래 참조)
    ├── lidar_link              차체 최상면 위 (LD19 360도 시야 확보)
    ├── imu_link                차체 질량중심 근처
    └── camera_link
        └── camera_optical_link  REP-103 광학 프레임 (z 전방/x 우측/y 하방)
```

`base_link`를 구동축 중심에 둔 이유: 차동구동의 순간회전중심이 구동축 위에 있어
odom·cmd_vel 계산과 rotate-in-place 정책이 단순해진다.

## 기본 형상 (기본 인자)

| 항목 | 값 |
|---|---|
| 총질량 | 60.0 kg |
| 질량중심 | x = −0.160 m, y = 0, z = 0.206 m |
| 캐스터 하중비 | 0.400 (명세 §3의 60:40) |
| 구동륜 | Ø200 × 50 mm, y = ±0.225 m |
| 캐스터 | Ø100 mm, x = −0.4 m, y = ±0.2 m |
| 차체 박스 | 700(D) × 550(W) × 360(H) mm, 전고 400 mm |
| LiDAR 높이 | 0.42 m |

**무게배분은 상수로 적지 않고 비율에서 역산한다.** 지지점이 구동축(x=0)과
캐스터축(x=−wheelbase) 두 곳이므로 캐스터 하중비는 전체 질량중심 x로 결정된다.
차체 질량중심 x를 목표 비율에서 풀어 쓰기 때문에 질량·배분비·치수를 바꿔도 60:40이
유지된다. 자세한 유도는 [`urdf/robot_params.xacro`](urdf/robot_params.xacro)의 주석에 있다.

## 캐스터는 근사다

실물은 스위블 캐스터지만 여기서는 **조인트 없는 저마찰 구(sphere)**로 근사했다.
스위블 축의 회전 저항 — 정지 상태에서 바퀴가 진행방향으로 틀어질 때 생기는 저항 —
을 모사하지 못한다. 이 저항이 명세 §1 검증항목 3 "피벗턴 시 캐스터 저항에 의한 경로
밀림"의 원인이므로, **구형 근사만으로는 그 현상이 재현되지 않는다.** 등가 마찰계수
(`caster_mu`)로 크기만 흉내낸다. 명세 §8 리스크대로 Phase 4에서 조인트 기반 캐스터
상세화를 검토한다.

## 치수의 출처

모든 치수는 [`config/robot_dimensions.yaml`](config/robot_dimensions.yaml)에
`{value, confidence, source}` 형태로 근거와 함께 들어 있다.

| confidence | 의미 |
|---|---|
| `spec` | 명세 §3에 명시된 확정 기준값 |
| `spec_draft` | 명세 §3의 "가안". 시뮬 검증 결과로 확정한다 (차체폭, 바퀴간격 등) |
| `todo` | 명세에도 없는 값. 임의 설정했으므로 설계 확정 시 교체 필요 |

`urdf/robot_params.xacro`의 기본값이 이 yaml과 일치하는지 테스트가 검사한다.
두 곳이 갈라지면 launch와 직접 렌더가 서로 다른 로봇을 만든다.

## 사용법

```bash
# RViz 확인
ros2 launch returnbot_description display.launch.py

# Phase 3 매트릭스 실험 — 인자만 바꾼다
ros2 launch returnbot_description display.launch.py body_width:=0.65 wheel_separation:=0.5

# URDF 렌더 + 검증
xacro urdf/returnbot.urdf.xacro > /tmp/returnbot.urdf && check_urdf /tmp/returnbot.urdf
xacro urdf/returnbot.urdf.xacro body_width:=0.65 > /tmp/wide.urdf
```

노출 인자: `wheel_separation` `body_width` `body_depth` `body_height` `wheel_radius`
`wheelbase` `total_mass`.

## 검증

```bash
python -m pytest tests -q      # ROS 없이도 동작
```

`check_urdf`가 하는 검사(단일 루트·순환 없음·트리 무결성)를 순수 파이썬으로 수행하고,
거기에 더해 순기구학으로 실제 형상을 검증한다:

- 구동륜·캐스터가 **모두 지면에 닿는지** (하나라도 뜨면 Gazebo에서 로봇이 기운다)
- 캐스터 하중비가 정확히 0.40인지 — wheelbase 3종에 대해
- 관성이 치수 공식과 일치하고 삼각부등식을 만족하는지 (위반하면 솔버 발산)
- 카메라 광학 프레임이 REP-103을 따르는지
- `body_width`/`wheel_separation` 인자가 비주얼·콜리전 양쪽에 반영되는지
- xacro 기본값이 `robot_dimensions.yaml`과 동기화되어 있는지

### ROS 2 실환경 (2026-08-31 완료)

- [x] `check_urdf` 통과 — base_footprint 루트, 9개 자식 링크 트리 정상
- [x] `body_width` 0.55/0.60/0.65 재렌더 + `check_urdf` 통과
- [x] `display.launch.py` 기동 → `tf2_echo` 로 9개 프레임 전부 확인.
      순수 파이썬 순기구학 예측치와 소수점 셋째 자리까지 일치
- [x] RViz2 WSLg 기동 (OpenGL 4.2)

`bash scripts/verify_phase1.sh` 로 전부 재현된다.
