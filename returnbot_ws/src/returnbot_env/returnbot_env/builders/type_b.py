"""유형 B — 중복도형.

양쪽 벽면에 세대문이 마주본다. 유효폭 1.8 m가 법정 최소값이다
(피난·방화규칙 §15의2① "양옆에 거실이 있는 복도", docs/env_reference.md §1.1).

시뮬 포인트는 **마주보는 세대의 동시 배출**이다. 양쪽 문 앞에 적치물이
동시에 놓이면 실효 통로폭이 급격히 줄어드는 상황을 재현한다.
"""

from __future__ import annotations

from ..config import EnvConfig
from ..ir import Scene
from ..params import EnvParams
from . import common


def build(cfg: EnvConfig, params: EnvParams) -> Scene:
    geo = common.corridor_geometry(cfg, params)
    scene = Scene(name=f"apt_type_b_w{params.corridor_width:.2f}".replace(".", "p"))

    common.add_corridor_floor(scene, cfg, params, geo)
    doors_pos = common.add_door_side_wall(scene, cfg, params, geo, +1, "wall_pos")
    doors_neg = common.add_door_side_wall(scene, cfg, params, geo, -1, "wall_neg")
    common.add_end_caps(scene, cfg, params, geo)

    if len(doors_pos) >= 2:
        common.add_hydrant_box(scene, cfg, geo, -1, (doors_neg[0] + doors_neg[1]) / 2.0)

    for i, x in enumerate(doors_pos):
        common.add_milk_box(scene, cfg, geo, +1, i, x)

    anchors = [(x, +1) for x in doors_pos] + [(x, -1) for x in doors_neg]
    placed = common.add_clutter(scene, cfg, params, geo, anchors)

    scene.metadata = {
        "type": "B",
        "label": params.label,
        "params": params.as_dict(),
        "derived": {
            "corridor_clear_width": geo.width,
            "ramp_x0": geo.ramp_x0,
            "ramp_x1": geo.ramp_x1,
            "ramp_rise": geo.ramp_rise,
            "door_x": doors_pos,
            "door_side_sign": 0,  # 양측
            "clutter_placed": placed,
        },
    }
    return scene
