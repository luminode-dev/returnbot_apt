# Phase 0 리포트 — 환경 기준 정리 및 파라메트릭 월드 생성기

명세 §6 Phase 0. 작성일 2026-08-30.

## 완료 기준 대비

명세: **"인자만 바꿔 3유형 월드가 생성되고 스크린샷이 docs에 저장됨"**

| 항목 | 상태 | 근거 |
|---|---|---|
| `docs/env_reference.md` 작성 | 완료 | [env_reference.md](env_reference.md) |
| 파라메트릭 월드 생성기 골격 | 완료 | [returnbot_env](../returnbot_ws/src/returnbot_env/) |
| 인자만 바꿔 3유형 생성 | 완료 | `python -m returnbot_env.cli --all` |
| 동일 소스에서 SDF + USD | **부분** | 공용 IR + SDF 완료, USD는 인터페이스만 (아래 참조) |
| 스크린샷 docs 저장 | **대체 충족** | Gazebo 실행 불가 → SVG 평면도 5종 커밋 |

## 산출물

### 문서
- [`docs/env_reference.md`](env_reference.md) — 치수 근거 문서. 확정/참고/TODO 3등급으로 출처 관리

### 코드 — `returnbot_ws/src/returnbot_env/`
```
EnvParams ──▶ builders/(A·B·C) ──▶ ir.Scene ──┬─▶ backends/sdf.py → Gazebo .sdf
 (yaml+CLI)                        (중립 IR)   ├─▶ backends/svg.py → 평면도 .svg
                                               └─▶ backends/usd.py → Phase 4
```
치수는 전부 [`config/env_types.yaml`](../returnbot_ws/src/returnbot_env/config/env_types.yaml)에
`{value, confidence, source}` 형태로 근거와 함께 들어 있다. 코드에 치수 리터럴 없음 (명세 §7).

### 평면도 (스크린샷 대체물) — `docs/phase0/`
| 파일 | 내용 |
|---|---|
| `apt_type_a.svg` | 편복도 1.2 m — **기준 월드(최악 조건)** |
| `apt_type_b.svg` | 중복도 1.8 m |
| `apt_type_c.svg` | 계단식 홀형 3.4 × 4.2 m |
| `apt_type_a_worstcase.svg` | 편복도 0.9 m + 문턱 20 mm (대수선 완화 규정 케이스) |
| `apt_type_b_cluttered.svg` | 중복도 + 적치물 밀도 1.0, seed 42 (양측 동시 배출) |

## 구현 범위

**월드 구성요소**: 세대문 우묵이(alcove)·인방·문턱, 경사로 단차, 편복도 개방측 난간,
옥내소화전함(벽 돌출), 우유함, 세대 앞 적치물(시드 기반 결정적 배치), 방화문 개폐 2상태,
승강기 뱅크, 홀 기둥, 주간 자연광.

**세대문 우묵이 처리**: CSG 없이 벽을 문 개구부에서 끊어 세그먼트로 만들고 문짝을 뒤로
물려 넣었다. 우묵이 깊이(0.1 m)가 벽 두께(0.2 m) 이하이므로 alcove 측면은 인접 세그먼트의
절단면이 그대로 담당한다. 로봇의 세대문 앞 정차 여유에 직접 영향을 주는 부분이라
근사하지 않고 실제 형상으로 만들었다.

**Gazebo 계열 이중화**: `--flavor fortress|harmonic`. 명세 §4는 `gz sim` 표기지만 ROS 2 Humble의
tier-1 페어링은 Fortress(`ign gazebo`)이고 시스템 플러그인 이름이 다르다. 최종 결정은 WSL
환경 구축 후 `env_reference.md` §6에 기록한다.

## 검증

```
$ python -m pytest tests -q
55 passed
```

Gazebo 없이 확인 가능한 것만 다뤘다:

- **복도 유효폭 실측 정합** — 생성된 지오메트리에서 좌우 벽 안쪽면 간격을 실측해 지정
  폭과 일치하는지 확인. 0.9/1.2/1.5/1.8 m × 유형 A/B 8조합. 이 값이 틀리면 Phase 3
  차체폭 매트릭스 실험 전체가 무의미해지므로 최우선 검증 항목으로 뒀다
- 적치물이 벽을 뚫지 않음 (회전한 자전거의 y방향 반폭 반영)
- 시드 결정성 — 같은 시드는 같은 배치, 다른 시드는 다른 배치
- 문턱 높이·경사로 구배가 인자를 따름, 경사로 뒤 세대의 문턱이 올라간 바닥 위에 놓임
- SDF/SVG가 유효한 XML, flavor에 따라 플러그인 네임스페이스가 바뀜
- 모든 yaml 치수가 출처를 가짐, 법정 확정치(1.2/1.8/0.8 m)가 유지됨

### 검증 중 잡은 결함 3건
1. **`--threshold` 인자가 무시됨** — 문턱 생성 코드가 params 대신 yaml 기본값을 직접
   읽고 있었다. 문턱은 명세 §8이 지목한 주행 성패 결정 요소라 치명적이었다
2. **적치물이 벽을 관통** — 회전한 1.7 m 자전거의 y방향 확장을 고려하지 않아 벽 안으로
   파고들었다. Gazebo에서 물리가 폭주할 형상이었다
3. **방화문 열림 문짝이 홀 한가운데 떠 있음** — 경첩 위치 계산 오류

## 알려진 한계

- **USD 백엔드 미구현**. Isaac Sim이 없는 상태에서 만든 USD는 로드 검증이 불가능해
  "돌아가는지 모르는 코드"가 된다. IR 계약을 `backends/usd.py` docstring에 고정해 두고
  Phase 4로 이월했다
- **Gazebo 실행 검증 없음**. SDF가 유효한 XML이고 구조가 맞다는 것까지만 확인했다.
  실제 로드·물리 거동은 Phase 2에서 확인한다
- **동적 장애물(보행자) 없음**. 명세 §2.2의 "동적/정적 랜덤 배치" 중 정적만 구현
- **텍스처 없음**. 명세 §2.3에 따라 Phase 0~3은 콜리전 정확도 우선

## 근거 미확보 치수 25건

`python -m returnbot_env.cli --list-todo` 로 전체 목록을 볼 수 있다. 명세 서문 규칙대로
그럴듯한 숫자로 메우지 않았고, 전부 인자로 노출해 yaml만 고치면 되게 해뒀다.

**실측 우선순위**:
1. `common.threshold.height` — 문턱 높이. 주행 성패를 직접 가른다
2. `common.hydrant_box.protrusion` — 소화전함 돌출. 1.2 m 복도의 유효폭을 실질적으로 잠식
3. `common.door.width` / `common.door.pitch` — 세대문 폭·간격
4. `types.C.hall_width` / `hall_depth` — 홀 치수. 현재는 승강기 전면 활동공간에서 역산한 잠정값

## 명세 정정 필요 사항

1. **§2.1 근거 문서** — 복도 1.2/1.8 m의 출처는 「주택건설기준 등에 관한 규정」이 아니라
   **「건축물의 피난·방화구조 등의 기준에 관한 규칙」 제15조의2 제1항**이다. 수치는 맞다
2. **§2.2 승강기 문 폭** — `0.9 m TODO(확인)`으로 뒀으나 법정 최소는 **0.8 m**이고 0.9 m는
   신축 기준이다. 로봇 승강기 진입 시나리오에서 0.8 m가 최악 조건이므로 기본값을 0.8로 뒀다
3. **§4 Gazebo 표기** — `gz sim`은 Garden/Harmonic 계열 명령어다. Fortress로 확정되면
   `ign gazebo`로 수정 필요

## 다음 단계

- Phase 1: URDF 모델링 (작성 완료, 검증은 WSL 구축 후)
- WSL2 + Ubuntu 22.04 + ROS 2 Humble 환경 구축 → Gazebo 계열 확정
- Phase 2에서 이 월드들을 실제로 로드해 SDF 유효성을 최종 확인
