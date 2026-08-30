"""유형별 월드 빌더. EnvParams → ir.Scene."""

from __future__ import annotations

from ..config import EnvConfig
from ..ir import Scene
from ..params import EnvParams
from . import common, type_a, type_b, type_c

BUILDERS = {
    "A": type_a.build,
    "B": type_b.build,
    "C": type_c.build,
}

__all__ = ["BUILDERS", "build_scene", "common", "type_a", "type_b", "type_c"]


def build_scene(cfg: EnvConfig, params: EnvParams) -> Scene:
    try:
        builder = BUILDERS[params.apt_type]
    except KeyError:  # pragma: no cover - params 검증에서 먼저 걸린다
        raise ValueError(f"빌더가 없는 유형: {params.apt_type}") from None
    return builder(cfg, params)
