# 기준 맵

Phase 2에서 slam_toolbox 로 만든 유형별 기준 맵. Phase 3의 AMCL 이 이 맵을 쓴다.

| 파일 | 크기 | 내용 |
|---|---|---|
| `apt_type_a` | 20.20 × 1.45 m | 편복도 1.2 m — 최악 조건 기준 월드 |
| `apt_type_b` | 20.15 × 2.10 m | 중복도 1.8 m |
| `apt_type_c` | 5.20 × 5.00 m | 계단식 홀형 |

**생성 조건**: 방화문 닫힘 + 적치물 없음 + 경사로 8% + 문턱 15 mm.

- 방화문을 열면 문 너머에 계단실이 없어 LiDAR 광선이 무한히 빠져나가 맵에 허위
  자유공간이 생긴다.
- 적치물은 이동 가능한 물체라 맵이 아니라 Nav2 코스트맵의 동적 장애물로 다뤄야 한다.
- 복도 맵핑은 제자리 선회 없이 전진-후진으로 한다. 선회 중 캐스터 근사 자세 오차가
  맵에 부채꼴 아티팩트로 찍힌다 (docs/phase2_report.md 참조).

재생성:

```bash
bash scripts/run_mapping.sh all      # 3유형
bash scripts/run_mapping.sh A        # 하나만
GUI=1 bash scripts/run_mapping.sh A  # 화면 띄운 채로
```
