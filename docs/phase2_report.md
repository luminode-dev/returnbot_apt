# Phase 2 리포트 — Gazebo 주행 검증 및 SLAM 맵핑

명세 §6 Phase 2. 작성일 2026-09-06.

## 완료 기준 대비

명세: **"3유형 주행·맵핑 정상"**

| 항목 | 상태 | 근거 |
|---|---|---|
| diff_drive·LiDAR·IMU 플러그인 | 완료 | Gazebo Fortress, `returnbot_sim/urdf/gazebo_plugins.xacro` |
| `/cmd_vel` `/scan` `/odom` 표준 네이밍 | 완료 | ros_gz_bridge, 아래 토픽표 |
| Phase 0 생성기로 월드 3종 × 문턱 15 mm × 경사로 8% | 완료 | `ramp_grade` / `threshold` launch 인자 |
| 텔레옵 주행 | 완료 | `teleop.launch.py` (사람) + `drive_mapping_run.py` (재현 가능) |
| slam_toolbox 맵 저장, 유형별 3개 맵 커밋 | 완료 | `returnbot_navigation/maps/apt_type_{a,b,c}` |

## 산출물

```
returnbot_ws/src/returnbot_sim/
├── urdf/gazebo_plugins.xacro     # diff_drive / gpu_lidar / imu / joint_state + 마찰
├── urdf/returnbot_gz.urdf.xacro  # description 모델 + 위 플러그인
├── config/spawn_poses.yaml       # 유형별 스폰 위치
├── config/slam_toolbox.yaml      # 복도 특성에 맞춘 SLAM 설정
├── launch/gazebo.launch.py       # 월드 자동생성 + 스폰 + 브릿지 + RViz
├── launch/mapping.launch.py      # 위 + slam_toolbox
├── launch/teleop.launch.py
└── scripts/drive_mapping_run.py  # /odom 폐루프 자동 주행

returnbot_ws/src/returnbot_navigation/maps/apt_type_{a,b,c}.{pgm,yaml}
scripts/run_mapping.sh            # 유형별 맵핑 1회 실행 → 저장까지
```

**패키지 분리 원칙**: `returnbot_description` 에는 Gazebo 태그를 넣지 않았다 (명세 §7).
시뮬 전용 요소는 전부 `returnbot_sim` 에 있고, 차체 치수 인자는 description 것을
그대로 물려받아 Phase 3 매트릭스가 같은 인자로 시뮬까지 돈다.

## 토픽

| 토픽 | 방향 | 타입 | 비고 |
|---|---|---|---|
| `/cmd_vel` | ROS → GZ | `geometry_msgs/Twist` | DiffDrive |
| `/odom` | GZ → ROS | `nav_msgs/Odometry` | `odom` → `base_footprint` |
| `/tf` | GZ → ROS | `tf2_msgs/TFMessage` | |
| `/scan` | GZ → ROS | `sensor_msgs/LaserScan` | `frame_id: lidar_link`, 360 샘플, 12 m |
| `/imu` | GZ → ROS | `sensor_msgs/Imu` | |
| `/joint_states` | GZ → ROS | `sensor_msgs/JointState` | 구동륜 2축 |
| `/clock` | GZ → ROS | `rosgraph_msgs/Clock` | `use_sim_time` |

## 검증 결과

### 지오메트리 정합 (LiDAR 실측 vs 월드)
유형 A(복도 유효폭 1.2 m), 로봇 스폰 x=1.5:

| 방향 | 실측 | 기대 | |
|---|---|---|---|
| 좌 90° | 0.61 m | 0.60 m (복도 반폭) | ✓ |
| 우 −90° | 0.60 m | 0.60 m | ✓ |
| 후방 180° | 1.34 m | 1.332 m (LiDAR x=1.332 → 끝벽 x=0) | ✓ |
| 전방 0° | inf | 12 m 사거리 밖 | ✓ |

### 주행 (유형 A/B, 15 m 전진 + 15 m 복귀)
경사로 8%(단차 150 mm)와 문턱 15 mm를 넘어 목표 거리를 정확히 주행했고,
**최종 odom 복귀 오차가 x=0.00 / y=0.00 / yaw=0°** 다.

### 맵

| 유형 | 맵 크기 | 점유 | 미지 | 내용 |
|---|---|---|---|---|
| A 편복도 | 404×29 = 20.20 × 1.45 m | 1310 | 1110 | 한쪽 벽 세대문 우묵이 5개 |
| B 중복도 | 403×42 = 20.15 × 2.10 m | 1157 | 1481 | 양쪽 벽 우묵이 5개씩 |
| C 홀형 | 104×100 = 5.20 × 5.00 m | 745 | 4280 | 닫힌 홀, 승강기·세대문 |

맵 크기가 월드 치수와 정확히 일치한다. 세대문 우묵이가 벽면의 톱니로 보이는 것까지
확인했다 — Phase 0에서 CSG 없이 만든 alcove 형상이 스캔에 그대로 잡힌다는 뜻이다.

## 핵심 발견 — 제자리 선회가 맵을 망친다

초기 맵에는 벽을 관통하는 **큰 부채꼴 허위 자유공간**이 있었다. 대조 실험으로
원인을 확정했다.

| 실험 | 결과 | 함의 |
|---|---|---|
| 편도 주행 (선회 없음) | **아티팩트 전무**, 맵 20.20 × 1.45 m | 선회가 원인 |
| `ramp_grade:=0` (평탄 복도) | 아티팩트 그대로 | 경사로 무관 |
| 유형 C (360° 회전 2회) | 깨끗함 | 회전 자체가 아니라 **긴 복도**가 조건 |

**기전**: 20 m 복도에서 LD19 사거리는 12 m라 복도 축 방향 광선은 항상 `inf` 다.
slam_toolbox 는 `inf` 광선을 최대사거리까지 자유공간으로 레이트레이싱한다.
제자리 선회 중에는 **캐스터 구형 근사** 탓에 자세 오차가 생기고, 그 순간의 `inf`
광선이 벽을 관통하는 대각선으로 찍힌다. 유형 C가 멀쩡한 이유는 홀이 좁아 모든
광선이 벽에 닿아 `inf` 가 없기 때문이다.

**이것은 명세 §8이 예견한 캐스터 모델 한계가 맵에 드러난 형태다.** 선회 속도를
0.5 → 0.3 rad/s 로 낮추자 odom 복귀 오차가 y=−0.13 m / yaw=1° → y=−0.04 m / yaw=0°
로 개선됐는데(= 스키드가 줄었다는 증거), 맵 아티팩트는 남았다.

**대응**: 복도 맵핑은 전진 후 **후진**으로 복귀한다. LiDAR가 360°라 관측 손실이 없다.
선회 성능 자체(명세 §1 검증항목 3의 피벗턴 경로 밀림)는 Phase 3 주행 평가에서
별도로 측정한다.

## 그 밖에 잡은 문제

1. **WSLg에서 gpu_lidar가 동작하지 않음.** 기본 GL 드라이버로는 ogre2가
   `Ogre::UnimplementedException(GL3PlusTextureGpu::copyTo)` 로 서버째 죽고,
   ogre1은 죽지 않는 대신 **전 방향 range_min(0.05 m)** 인 쓰레기 스캔을 낸다.
   `LIBGL_ALWAYS_SOFTWARE=1`(llvmpipe)로 두 엔진 모두 정상화됐다. RTF는 99.7%로
   느려지지 않았다. Gazebo 프로세스에만 걸어 RViz는 하드웨어 GL을 쓰게 했다.
2. **LiDAR 하우징 콜리전이 스캔을 죽임.** 고정 조인트 링크는 SDF 변환에서 부모로
   합쳐지므로 광선이 자기 하우징(반경 0.03 m)을 먼저 때려 range_min으로 클램프됐다.
   콜리전을 제거하고 회귀 테스트를 추가했다.
3. **`use_sim_time` 시계 동기화 전 deadline 계산.** 첫 `/clock` 전에는 ROS 시계가
   0이라 `deadline = 0 + 30`이 되고, 시계가 시뮬 경과시간으로 튀는 순간 즉시
   타임아웃된다. 이 때문에 주행이 통째로 건너뛰어지고 정지 상태 맵만 저장됐다.
4. **반복 횟수로 시간을 세던 타임아웃.** `spin_once` 는 메시지가 있으면 곧바로
   반환하므로 180초 타임아웃이 실제로는 3.5초 만에 걸렸다.
5. **`--symlink-install` 과 실행 권한.** 소스 파일에 실행 비트가 없어
   `ros2 run` 이 실행파일을 찾지 못했다.

## 부수 소득 — Phase 3 매트릭스로 넘길 관측

**1.2 m 편복도 + 세대 앞 유모차는 차체 550 mm 로 사실상 통과 불가다.**
seed 0에서 유모차가 x=14.4, y=0.23에 놓이면 남는 통로가 0.605 m로 편측 여유가
**2.75 cm** 다. 실제로 로봇이 들이받고 멈춰 맵핑이 타임아웃됐다.
명세 Phase 3의 차체폭 매트릭스에서 정량화할 항목이다.

## 설정 판단

- **기준 맵은 방화문 닫힘 + 적치물 없음.** 방화문을 열면 문 너머에 계단실이 없어
  광선이 무한히 빠져나간다. 적치물은 이동 가능한 물체라 Nav2 코스트맵의 동적
  장애물로 다루는 것이 맞고 맵에 구워 넣으면 안 된다. 두 조건 모두 launch 인자
  (`fire_door`, `clutter`)로 켤 수 있고, 월드 파일명에 조건이 인코딩된다.
- **자동 주행으로 맵 생성.** 손 텔레옵은 매번 다른 맵이 나와 Phase 3 기준 맵으로
  쓸 수 없다. `teleop.launch.py` 는 사람이 몰아보는 용도로 남겼다.

## 알려진 한계

- **캐스터는 여전히 구형 근사다.** 위 발견이 그 대가를 보여준다. 명세 §8대로
  Phase 4에서 조인트 기반 상세화를 검토한다.
- **마찰계수는 전부 튜닝 시작점** (`robot_dimensions.yaml` friction 절, 전부 TODO).
  실기 실측 전까지 문턱·경사로 통과 판정을 절대값으로 믿으면 안 된다.
- **동적 장애물(보행자) 없음.** 명세 §2.2의 정적 배치만 구현.
- **방화문 너머 계단실 공간이 월드에 없다.** `fire_door:=open` 시나리오를 제대로
  쓰려면 Phase 0 생성기에 계단실 공간을 추가해야 한다.
- **소화전함이 LiDAR에 안 보인다.** 설치 높이 0.6 m + 함 높이 0.8 m 라 스캔면
  0.42 m 아래를 지나간다. 실제로 복도 유효폭을 잠식하는 장애물인데 2D LiDAR로는
  검출되지 않는다 — Phase 3 코스트맵에서 별도 처리가 필요하다.

## 다음 단계 (Phase 3)

1. AMCL + Nav2 구성 (Pi 5 성능 고려: controller 20 Hz, costmap 0.05 m 시작점)
2. 미션: 엘리베이터홀 출발 → 세대문 앞 순차 정차 3초 → 복귀
3. rotate-in-place 후 출발 정책, **피벗턴 경로 밀림 측정** — Phase 2에서 그 존재가
   이미 확인됐으므로 정량화가 목표
4. 매트릭스: 차체폭 550/600/650 × 유형 A(1.2 m)/B(1.8 m)/C(홀)
5. 적치물 랜덤 배치 시나리오 (`clutter:=true`)에서 회피·미션 유지율
