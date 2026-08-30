"""파라메트릭 월드 생성기 CLI.

사용 예:
    python -m returnbot_env.cli --type A
    python -m returnbot_env.cli --type A --corridor-width 0.9 --threshold 0.020
    python -m returnbot_env.cli --all --svg-dir ../../../docs/phase0

명세 §6 Phase 0 완료 기준: "인자만 바꿔 3유형 월드가 생성"되어야 한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backends import sdf as sdf_backend
from .backends import svg as svg_backend
from .builders import build_scene
from .config import EnvConfig
from .params import APARTMENT_TYPES, build_params

DEFAULT_WORLD_DIR = Path(__file__).resolve().parent.parent / "worlds"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="returnbot_env",
        description="한국 아파트 공용부 파라메트릭 월드 생성기 (Gazebo SDF + 평면도 SVG)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--type", dest="apt_type", choices=list(APARTMENT_TYPES), help="아파트 유형")
    p.add_argument("--all", action="store_true", help="A/B/C 세 유형을 한 번에 생성")
    p.add_argument("--config", type=Path, default=None, help="env_types.yaml 경로")

    g = p.add_argument_group("치수 오버라이드 (미지정 시 env_types.yaml 값)")
    g.add_argument("--corridor-width", type=float, default=None, help="복도 유효폭 [m] (A/B)")
    g.add_argument("--corridor-length", type=float, default=None, help="복도 길이 [m] (A/B)")
    g.add_argument("--hall-width", type=float, default=None, help="홀 폭 [m] (C)")
    g.add_argument("--hall-depth", type=float, default=None, help="홀 깊이 [m] (C)")
    g.add_argument("--units", type=int, default=None, dest="unit_count", help="세대수")
    g.add_argument("--threshold", type=float, default=None, dest="threshold_height",
                   help="문턱 높이 [m]")
    g.add_argument("--ramp-grade", type=float, default=None, help="경사로 구배 (0.08 = 8%%)")
    g.add_argument("--ramp-rise", type=float, default=None, help="경사로 단차 [m]")
    g.add_argument("--elevator-door-width", type=float, default=None,
                   help="승강기 출입문 유효폭 [m] (법정 최소 0.8)")

    o = p.add_argument_group("장애물·시나리오")
    o.add_argument("--obstacle-density", type=float, default=None,
                   help="세대당 적치물 배치 확률 0..1")
    o.add_argument("--no-clutter", action="store_true", help="적치물을 아예 배치하지 않음")
    o.add_argument("--fire-door-closed", action="store_true", help="방화문 닫힘 상태")
    o.add_argument("--seed", type=int, default=None, help="적치물 배치 난수 시드 (재현성)")

    out = p.add_argument_group("출력")
    out.add_argument("--out", type=Path, default=DEFAULT_WORLD_DIR, help="SDF 출력 디렉터리")
    out.add_argument("--svg-dir", type=Path, default=None,
                     help="평면도 SVG 출력 디렉터리 (미지정 시 생성 안 함)")
    out.add_argument("--flavor", choices=("fortress", "harmonic"), default="fortress",
                     help="Gazebo 시스템 플러그인 계열")
    out.add_argument("--name", default=None, help="출력 파일 basename 강제 지정")
    out.add_argument("--list-todo", action="store_true",
                     help="근거 미확보(TODO) 치수를 출력하고 종료")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = EnvConfig.load(args.config)

    if args.list_todo:
        todos = cfg.todo_items()
        print(f"근거 미확보 치수 {len(todos)}건 (docs/env_reference.md §4 참조)")
        for item in todos:
            print(f"  - {item.path} = {item.value}\n      {item.source}")
        return 0

    if not args.apt_type and not args.all:
        build_parser().error("--type 또는 --all 중 하나가 필요하다")

    types = list(APARTMENT_TYPES) if args.all else [args.apt_type]

    overrides = {
        "corridor_width": args.corridor_width,
        "corridor_length": args.corridor_length,
        "hall_width": args.hall_width,
        "hall_depth": args.hall_depth,
        "unit_count": args.unit_count,
        "threshold_height": args.threshold_height,
        "ramp_grade": args.ramp_grade,
        "ramp_rise": args.ramp_rise,
        "elevator_door_width": args.elevator_door_width,
        "obstacle_density": args.obstacle_density,
        "seed": args.seed,
        "include_clutter": False if args.no_clutter else None,
        "fire_door_closed": True if args.fire_door_closed else None,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    if args.svg_dir:
        args.svg_dir.mkdir(parents=True, exist_ok=True)

    for apt_type in types:
        applicable = _applicable_overrides(apt_type, overrides)
        params = build_params(cfg, apt_type, **applicable)
        scene = build_scene(cfg, params)

        basename = args.name or f"apt_type_{apt_type.lower()}"
        sdf_path = args.out / f"{basename}.sdf"
        sdf_path.write_text(sdf_backend.to_sdf(scene, args.flavor), encoding="utf-8", newline="\n")
        print(f"[SDF] {sdf_path}  ({len(scene)} elements)")

        if args.svg_dir:
            svg_path = args.svg_dir / f"{basename}.svg"
            svg_path.write_text(svg_backend.to_svg(scene), encoding="utf-8", newline="\n")
            print(f"[SVG] {svg_path}")

    return 0


def _applicable_overrides(apt_type: str, overrides: dict) -> dict:
    """유형에 맞지 않는 인자는 조용히 버린다 (--all 로 한 번에 돌릴 때 필요)."""
    corridor_only = {"corridor_width", "corridor_length"}
    hall_only = {"hall_width", "hall_depth"}
    drop = hall_only if apt_type != "C" else corridor_only
    return {k: v for k, v in overrides.items() if k not in drop}


if __name__ == "__main__":
    sys.exit(main())
