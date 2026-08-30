# returnbot_env

한국 아파트 공용부 파라메트릭 월드 생성기 (명세 §6 Phase 0).

인자 하나만 바꾸면 편복도/중복도/엘리베이터홀 3유형 월드가 나온다. ROS 2 의존성이
없으므로 **ROS 없이 순수 파이썬만으로 실행·검증**할 수 있고, 동시에 colcon 패키지이기도 하다.

## 설계

```
EnvParams  ──▶  builders/  ──▶  ir.Scene  ──┬──▶ backends/sdf.py  → Gazebo .sdf
(yaml+CLI)     (A/B/C)      (중립 IR)       ├──▶ backends/svg.py  → 평면도 .svg
                                            └──▶ backends/usd.py  → Isaac USD (Phase 4)
```

명세 §6의 "Gazebo world(sdf)와 USD를 동일 소스에서 생성"을 `ir.Scene` 한 겹으로 만족시킨다.
백엔드는 IR만 소비하므로 USD 백엔드를 나중에 채워도 지오메트리가 갈라지지 않는다.

**좌표계**: X = 복도 길이축(주행 방향), Y = 복도 폭축(중심선 y=0), Z = 상방(기준 바닥 z=0).
회전은 SDF와 같은 RPY(R = Rz·Ry·Rx).

## 치수의 출처

모든 치수는 [`config/env_types.yaml`](config/env_types.yaml)에 `{value, confidence, source}`
형태로 근거와 함께 들어 있다. 코드에 치수 리터럴을 두지 않는다 (명세 §7).

| confidence | 의미 |
|---|---|
| `confirmed` | 법령 조문에 명시 (복도 1.2/1.8 m, 승강기 문 0.8 m 등) |
| `reference` | 공개자료 기반 또는 법령과 정합 (층고 2.8 m, 경사로 8%) |
| `todo` | **근거 미확보.** 임의 확정 금지 — 인자로만 노출 |

근거 상세는 [`docs/env_reference.md`](../../../docs/env_reference.md).

```bash
python -m returnbot_env.cli --list-todo    # 근거 미확보 치수 전체 목록
```

## 사용법

```bash
# 3유형 한 번에 (Phase 0 완료 기준)
python -m returnbot_env.cli --all --svg-dir ../../../docs/phase0

# 최악 조건 스윕: 대수선 완화 규정상 가능한 0.9 m 복도 + 문턱 20 mm
python -m returnbot_env.cli --type A --corridor-width 0.9 --threshold 0.020

# 중복도 양측 동시 배출 시나리오 (적치물 밀도 최대, 시드 고정)
python -m returnbot_env.cli --type B --obstacle-density 1.0 --seed 42

# 홀형 + 방화문 닫힘
python -m returnbot_env.cli --type C --fire-door-closed

python -m returnbot_env.cli --help
```

`--seed`가 같으면 적치물 배치가 항상 같다. Phase 3 매트릭스 실험의 재현성이 여기에 달려 있다.

### Gazebo 계열 선택

```bash
python -m returnbot_env.cli --type A --flavor fortress   # 기본, ign gazebo
python -m returnbot_env.cli --type A --flavor harmonic   # gz sim
```

명세 §4는 `gz sim` 표기지만 ROS 2 Humble의 tier-1 페어링은 Fortress다. 시스템 플러그인
이름이 달라서 인자로 분리해 두었다. 최종 결정은 WSL 환경 구축 시 apt 가용성을 보고
`docs/env_reference.md` §6에 기록한다.

## 검증

```bash
python -m pytest tests -q
```

Gazebo 없이 확인 가능한 것만 다룬다 — 생성된 지오메트리에서 **벽 안쪽면 간격을 실측해
지정 복도폭과 일치하는지**, 적치물이 벽을 뚫지 않는지, 시드가 결정적인지, SDF/SVG가
유효한 XML인지. 실제 물리 거동(문턱 통과, 마찰)은 Phase 2에서 Gazebo로 검증한다.

## 구현된 것 / 안 된 것

- 구현: 유형 A/B/C, 세대문 우묵이·인방·문턱, 경사로 단차, 소화전함, 우유함,
  적치물 시드 배치, 방화문 개폐 2상태, 승강기 뱅크, 홀 기둥, SDF/SVG 백엔드
- 미구현: USD 백엔드(Phase 4), 야간 조명·센서등(Phase 4), 동적 장애물(보행자),
  텍스처·포토리얼 에셋(Phase 4)
