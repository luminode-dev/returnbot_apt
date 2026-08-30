"""유형 C — 계단식(홀형).

복도가 없고 엘리베이터홀에 세대 2~4호가 붙는다. 최신 아파트의 주류 유형이다.
시뮬 포인트는 **홀 내 다점 정차와 제자리 회전**이다 (명세 §2.1).

좌표계: 홀은 x ∈ [0, hall_depth], y ∈ [-hall_width/2, +hall_width/2].
    x = 0  벽 : 승강기 (로봇 진입/대기면)
    x = D  벽 : 계단실 방화문
    ±y   벽 : 세대 현관문
"""

from __future__ import annotations

from ..config import EnvConfig
from ..ir import Box, Element, Pose, Scene
from ..params import EnvParams
from . import common
from .common import DOOR_PANEL_THICKNESS


def build(cfg: EnvConfig, params: EnvParams) -> Scene:
    depth = params.hall_depth
    width = params.hall_width
    geo = common.CorridorGeometry(
        length=depth,
        width=width,
        wall_thickness=float(cfg.get("common.wall_thickness")),
        wall_height=float(cfg.get("common.wall_height")),
        floor_thickness=float(cfg.get("common.floor_thickness")),
        ramp_x0=0.0,
        ramp_x1=0.0,
        ramp_rise=0.0,
        ramp_angle=0.0,
    )
    scene = Scene(name=f"apt_type_c_{width:.1f}x{depth:.1f}".replace(".", "p"))

    common.add_corridor_floor(scene, cfg, params, geo)

    # 세대 현관문을 양쪽 측벽에 나눠 붙인다 (3호면 +y 2호 / -y 1호).
    door_w = float(cfg.get("common.door.width"))
    n_pos = (params.unit_count + 1) // 2
    n_neg = params.unit_count - n_pos
    doors_pos = _spread(depth, n_pos, door_w)
    doors_neg = _spread(depth, n_neg, door_w)

    if doors_pos:
        common.add_door_side_wall(scene, cfg, params, geo, +1, "wall_pos", doors=doors_pos)
    else:
        common.add_plain_wall(scene, cfg, geo, "wall_pos", +1)
    if doors_neg:
        common.add_door_side_wall(scene, cfg, params, geo, -1, "wall_neg", doors=doors_neg)
    else:
        common.add_plain_wall(scene, cfg, geo, "wall_neg", -1)

    elevator_y = _add_elevator_bank(scene, cfg, params, geo)

    # 계단실 방화문 (x = depth 쪽)
    common.add_fire_door(
        scene,
        cfg,
        params,
        name="fire_door_stair",
        x=depth + geo.wall_thickness / 2.0,
        y=0.0,
        span=width + 2 * geo.wall_thickness,
        thickness=geo.wall_thickness,
        height=geo.wall_height,
        base_z=0.0,
        axis="x",
    )

    # 홀 내 기둥 (명세 §2.2). 승강기 전면 활동공간을 침범하지 않는 구석에 둔다.
    pillar_r = geo.wall_thickness
    common.add_pillar(
        scene,
        cfg,
        "hall_pillar",
        x=depth - pillar_r * 1.5,
        y=-(width / 2.0 - pillar_r * 1.5),
        radius=pillar_r,
        height=geo.wall_height,
    )

    anchors = [(x, +1) for x in doors_pos] + [(x, -1) for x in doors_neg]
    placed = common.add_clutter(scene, cfg, params, geo, anchors)

    front_clearance = float(cfg.get("common.elevator.front_clearance"))
    scene.metadata = {
        "type": "C",
        "label": params.label,
        "params": params.as_dict(),
        "derived": {
            "hall_width": width,
            "hall_depth": depth,
            "door_x_pos": doors_pos,
            "door_x_neg": doors_neg,
            "elevator_y": elevator_y,
            "elevator_front_clearance_required": front_clearance,
            "clutter_placed": placed,
        },
    }
    return scene


def _spread(length: float, count: int, door_w: float) -> list[float]:
    """벽 길이 안에 count개 문을 균등 배치한 중심 x 목록."""
    if count <= 0:
        return []
    margin = door_w
    usable = length - 2 * margin
    if usable <= 0:
        raise ValueError(f"홀 깊이 {length}m 가 세대문 배치에 부족하다")
    if count == 1:
        return [length / 2.0]
    step = usable / (count - 1)
    return [margin + i * step for i in range(count)]


def _add_elevator_bank(
    scene: Scene, cfg: EnvConfig, params: EnvParams, geo: common.CorridorGeometry
) -> list[float]:
    """x=0 벽에 승강기 출입문을 배치한다.

    문 폭은 법정 최소 0.8 m가 기본이다 (신축은 0.9 m). 로봇 승강기 진입
    시나리오에서 0.8 m가 최악 조건이므로 이 값을 기본으로 둔다.
    docs/env_reference.md §2 참조.
    """
    door_w = params.elevator_door_width
    door_h = float(cfg.get("common.door.height"))
    n = max(1, params.elevator_count)
    t = geo.wall_thickness
    height = geo.wall_height
    span = geo.width + 2 * t

    centers = _spread(geo.width, n, door_w)
    ys = [c - geo.half_width for c in centers]

    # 개구부를 비운 벽 세그먼트
    edges: list[tuple[float, float]] = []
    cursor = -span / 2.0
    for y in sorted(ys):
        edges.append((cursor, y - door_w / 2.0))
        cursor = y + door_w / 2.0
    edges.append((cursor, span / 2.0))

    for i, (y0, y1) in enumerate(edges):
        if y1 - y0 <= 1e-6:
            continue
        scene.add(
            Element(
                name=f"elev_wall_seg{i}",
                geometry=Box((t, y1 - y0, height)),
                pose=Pose(x=-t / 2.0, y=(y0 + y1) / 2.0, z=height / 2.0),
                material=cfg.material("concrete"),
                tags=("wall",),
            )
        )

    for i, y in enumerate(sorted(ys)):
        scene.add(
            Element(
                name=f"elev_door{i}",
                geometry=Box((DOOR_PANEL_THICKNESS, door_w, door_h)),
                pose=Pose(x=-DOOR_PANEL_THICKNESS / 2.0, y=y, z=door_h / 2.0),
                material=cfg.material("metal"),
                tags=("door", "elevator_door"),
            )
        )
        lintel_h = height - door_h
        if lintel_h > 1e-6:
            scene.add(
                Element(
                    name=f"elev_lintel{i}",
                    geometry=Box((t, door_w, lintel_h)),
                    pose=Pose(x=-t / 2.0, y=y, z=door_h + lintel_h / 2.0),
                    material=cfg.material("concrete"),
                    tags=("wall",),
                )
            )
    return sorted(ys)
