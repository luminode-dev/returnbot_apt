"""유형 A — 편복도(갓복도)형.

한쪽 벽면에만 세대문이 있고 반대편은 개방 난간이다.
복도 유효폭 1.2 m가 법규 최소값이므로 이 월드가 **최악 조건 기준 월드**다
(명세 §2.1, 근거는 docs/env_reference.md §1.1).
"""

from __future__ import annotations

from ..config import EnvConfig
from ..ir import Scene
from ..params import EnvParams
from . import common


def build(cfg: EnvConfig, params: EnvParams) -> Scene:
    geo = common.corridor_geometry(cfg, params)
    scene = Scene(name=f"apt_type_a_w{params.corridor_width:.2f}".replace(".", "p"))

    door_sign = 1 if params.door_side == "+y" else -1
    open_sign = -door_sign

    common.add_corridor_floor(scene, cfg, params, geo)
    doors = common.add_door_side_wall(scene, cfg, params, geo, door_sign, "wall_door")
    common.add_parapet(scene, cfg, geo, open_sign)
    common.add_end_caps(scene, cfg, params, geo)

    # 소화전함은 세대문 사이 벽면에 둔다. 문 개구부와 겹치지 않는 첫 빈 구간.
    if len(doors) >= 2:
        common.add_hydrant_box(scene, cfg, geo, door_sign, (doors[0] + doors[1]) / 2.0)

    for i, x in enumerate(doors):
        common.add_milk_box(scene, cfg, geo, door_sign, i, x)

    placed = common.add_clutter(scene, cfg, params, geo, [(x, door_sign) for x in doors])

    scene.metadata = {
        "type": "A",
        "label": params.label,
        "params": params.as_dict(),
        "derived": {
            "corridor_clear_width": geo.width,
            "ramp_x0": geo.ramp_x0,
            "ramp_x1": geo.ramp_x1,
            "ramp_rise": geo.ramp_rise,
            "door_x": doors,
            "door_side_sign": door_sign,
            "clutter_placed": placed,
        },
    }
    return scene
