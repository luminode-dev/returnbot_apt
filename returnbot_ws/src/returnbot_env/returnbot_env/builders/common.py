"""유형 A/B/C가 공유하는 지오메트리 헬퍼.

여기서 만드는 것은 전부 ir.Element 이고, 백엔드는 관여하지 않는다.
치수는 반드시 EnvConfig / EnvParams 에서 읽는다 (명세 §7 매직넘버 금지).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..config import EnvConfig
from ..ir import Box, Cylinder, Element, Material, Pose, Scene
from ..params import EnvParams

#: 문짝 패널 두께. 벽 두께 안에 우묵이와 함께 들어가야 하므로 얇게 잡는다.
DOOR_PANEL_THICKNESS = 0.04


@dataclass(frozen=True)
class CorridorGeometry:
    """복도형(A/B) 월드의 파생 치수. 한 번 계산해 모든 헬퍼가 공유한다."""

    length: float
    width: float
    wall_thickness: float
    wall_height: float
    floor_thickness: float
    ramp_x0: float
    ramp_x1: float
    ramp_rise: float
    ramp_angle: float

    @property
    def half_width(self) -> float:
        return self.width / 2.0

    @property
    def has_ramp(self) -> bool:
        return self.ramp_x1 > self.ramp_x0

    def floor_top_at(self, x: float) -> float:
        """x 위치의 바닥 상면 높이. 문턱·적치물을 얹을 때 쓴다."""
        if not self.has_ramp or x <= self.ramp_x0:
            return 0.0
        if x >= self.ramp_x1:
            return self.ramp_rise
        ratio = (x - self.ramp_x0) / (self.ramp_x1 - self.ramp_x0)
        return self.ramp_rise * ratio


def corridor_geometry(cfg: EnvConfig, params: EnvParams) -> CorridorGeometry:
    doors = door_positions(cfg, params)
    ramp_len = params.ramp_length
    ramp_x0, ramp_x1 = _ramp_span(params.corridor_length, doors, ramp_len)
    return CorridorGeometry(
        length=params.corridor_length,
        width=params.corridor_width,
        wall_thickness=float(cfg.get("common.wall_thickness")),
        wall_height=float(cfg.get("common.wall_height")),
        floor_thickness=float(cfg.get("common.floor_thickness")),
        ramp_x0=ramp_x0,
        ramp_x1=ramp_x1,
        ramp_rise=params.ramp_rise if ramp_len > 0 else 0.0,
        ramp_angle=math.atan(params.ramp_grade) if ramp_len > 0 else 0.0,
    )


def door_positions(cfg: EnvConfig, params: EnvParams) -> list[float]:
    """세대 현관문 중심의 x 좌표. 복도 길이 안에 균등 배치한다."""
    pitch = float(cfg.get("common.door.pitch"))
    n = params.unit_count
    span = (n - 1) * pitch
    if span > params.corridor_length:
        raise ValueError(
            f"세대 {n}개를 pitch {pitch}m 로 배치하려면 복도 길이가 {span}m 이상이어야 한다 "
            f"(현재 {params.corridor_length}m)"
        )
    start = (params.corridor_length - span) / 2.0
    return [start + i * pitch for i in range(n)]


def _ramp_span(length: float, doors: list[float], ramp_len: float) -> tuple[float, float]:
    """경사로를 세대문 사이 빈 구간에 끼워 넣는다. 자리가 없으면 경사로를 생략한다."""
    if ramp_len <= 0.0:
        return (0.0, 0.0)
    if len(doors) >= 2:
        i = len(doors) // 2 - 1
        gap_lo, gap_hi = doors[i], doors[i + 1]
        if gap_hi - gap_lo >= ramp_len:
            mid = (gap_lo + gap_hi) / 2.0
            return (mid - ramp_len / 2.0, mid + ramp_len / 2.0)
    # 세대문 사이에 자리가 없으면 복도 후반부에 둔다.
    x0 = 0.7 * length
    if x0 + ramp_len > length:
        return (0.0, 0.0)
    return (x0, x0 + ramp_len)


# --------------------------------------------------------------------- 바닥
def add_corridor_floor(scene: Scene, cfg: EnvConfig, params: EnvParams, geo: CorridorGeometry) -> None:
    """하단 바닥 → 경사로 → 상단 바닥. 경사로가 없으면 단일 슬래브."""
    mat = cfg.material(params.floor_material)
    t = geo.floor_thickness

    if not geo.has_ramp:
        _add_slab(scene, "floor", 0.0, geo.length, geo.width, t, 0.0, mat)
        return

    _add_slab(scene, "floor_lower", 0.0, geo.ramp_x0, geo.width, t, 0.0, mat)
    # 상단 슬래브는 단차만큼 두껍게 해서 지면(z=-t)까지 닿게 한다. 옆면에 빈틈이 생기지 않는다.
    _add_slab(
        scene, "floor_upper", geo.ramp_x1, geo.length, geo.width, t + geo.ramp_rise, geo.ramp_rise, mat
    )

    # 경사로: 기울인 슬래브. pitch=-θ 로 두면 +x 방향으로 올라간다.
    theta = geo.ramp_angle
    run = geo.ramp_x1 - geo.ramp_x0
    slope_len = run / math.cos(theta)
    top_mid_x = (geo.ramp_x0 + geo.ramp_x1) / 2.0
    top_mid_z = geo.ramp_rise / 2.0
    # 상면 법선(로컬 +Z)이 월드에서 (-sinθ, 0, cosθ) 이므로 그 반대로 반두께만큼 내린다.
    cx = top_mid_x + (t / 2.0) * math.sin(theta)
    cz = top_mid_z - (t / 2.0) * math.cos(theta)
    scene.add(
        Element(
            name="floor_ramp",
            geometry=Box((slope_len, geo.width, t)),
            pose=Pose(x=cx, y=0.0, z=cz, pitch=-theta),
            material=mat,
            tags=("floor", "ramp"),
        )
    )


def _add_slab(
    scene: Scene,
    name: str,
    x0: float,
    x1: float,
    width: float,
    thickness: float,
    top_z: float,
    mat: Material,
) -> None:
    if x1 <= x0:
        return
    scene.add(
        Element(
            name=name,
            geometry=Box((x1 - x0, width, thickness)),
            pose=Pose(x=(x0 + x1) / 2.0, y=0.0, z=top_z - thickness / 2.0),
            material=mat,
            tags=("floor",),
        )
    )


# ---------------------------------------------------------------------- 벽
def add_plain_wall(
    scene: Scene,
    cfg: EnvConfig,
    geo: CorridorGeometry,
    name: str,
    side_sign: int,
) -> None:
    """세대문이 없는 쪽의 통짜 벽."""
    mat = cfg.material("concrete")
    height = geo.wall_height + geo.ramp_rise
    scene.add(
        Element(
            name=name,
            geometry=Box((geo.length, geo.wall_thickness, height)),
            pose=Pose(
                x=geo.length / 2.0,
                y=side_sign * (geo.half_width + geo.wall_thickness / 2.0),
                z=height / 2.0,
            ),
            material=mat,
            tags=("wall",),
        )
    )


def add_door_side_wall(
    scene: Scene,
    cfg: EnvConfig,
    params: EnvParams,
    geo: CorridorGeometry,
    side_sign: int,
    prefix: str,
    doors: list[float] | None = None,
) -> list[float]:
    """세대문이 늘어선 벽. 문 개구부를 비운 벽 세그먼트 + 문 조립체로 만든다.

    개구부 측면(문설주)은 인접 세그먼트의 절단면이 그대로 담당하므로
    우묵이 깊이가 벽 두께 이하이면 CSG 없이 정확한 alcove가 나온다.

    doors 를 주면 그 x 위치를 쓰고, 없으면 params 로부터 균등 배치를 계산한다.
    (홀형은 벽마다 세대수가 달라 직접 지정한다.)
    """
    if doors is None:
        doors = door_positions(cfg, params)
    door_w = float(cfg.get("common.door.width"))
    mat = cfg.material("concrete")
    height = geo.wall_height + geo.ramp_rise
    y_wall = side_sign * (geo.half_width + geo.wall_thickness / 2.0)

    edges: list[tuple[float, float]] = []
    cursor = 0.0
    for x in doors:
        edges.append((cursor, x - door_w / 2.0))
        cursor = x + door_w / 2.0
    edges.append((cursor, geo.length))

    for i, (x0, x1) in enumerate(edges):
        if x1 - x0 <= 1e-6:
            continue
        scene.add(
            Element(
                name=f"{prefix}_seg{i}",
                geometry=Box((x1 - x0, geo.wall_thickness, height)),
                pose=Pose(x=(x0 + x1) / 2.0, y=y_wall, z=height / 2.0),
                material=mat,
                tags=("wall",),
            )
        )

    for i, x in enumerate(doors):
        add_door_assembly(scene, cfg, params, geo, side_sign, prefix, i, x)
    return doors


def add_door_assembly(
    scene: Scene,
    cfg: EnvConfig,
    params: EnvParams,
    geo: CorridorGeometry,
    side_sign: int,
    prefix: str,
    index: int,
    x: float,
) -> None:
    """우묵이 안의 문짝 + 상부 인방 + 뒤채움 + 문턱."""
    door_w = float(cfg.get("common.door.width"))
    door_h = float(cfg.get("common.door.height"))
    recess = float(cfg.get("common.door.recess_depth"))
    t = geo.wall_thickness
    if recess + DOOR_PANEL_THICKNESS > t:
        raise ValueError(
            f"우묵이 깊이({recess}) + 문짝 두께({DOOR_PANEL_THICKNESS}) 가 "
            f"벽 두께({t})를 넘는다. env_types.yaml 을 조정할 것"
        )

    base_z = geo.floor_top_at(x)
    inner = geo.half_width  # 복도쪽 벽 안쪽면
    panel_y = side_sign * (inner + recess + DOOR_PANEL_THICKNESS / 2.0)

    scene.add(
        Element(
            name=f"{prefix}_door{index}",
            geometry=Box((door_w, DOOR_PANEL_THICKNESS, door_h)),
            pose=Pose(x=x, y=panel_y, z=base_z + door_h / 2.0),
            material=cfg.material("door_panel"),
            tags=("door",),
        )
    )

    # 문짝 뒤 잔여 벽 두께를 메워 월드 외피를 닫는다.
    fill = t - recess - DOOR_PANEL_THICKNESS
    if fill > 1e-6:
        scene.add(
            Element(
                name=f"{prefix}_doorback{index}",
                geometry=Box((door_w, fill, geo.wall_height + geo.ramp_rise)),
                pose=Pose(
                    x=x,
                    y=side_sign * (inner + recess + DOOR_PANEL_THICKNESS + fill / 2.0),
                    z=(geo.wall_height + geo.ramp_rise) / 2.0,
                ),
                material=cfg.material("concrete"),
                tags=("wall",),
            )
        )

    # 문 위 인방
    lintel_h = geo.wall_height + geo.ramp_rise - (base_z + door_h)
    if lintel_h > 1e-6:
        scene.add(
            Element(
                name=f"{prefix}_lintel{index}",
                geometry=Box((door_w, recess + DOOR_PANEL_THICKNESS, lintel_h)),
                pose=Pose(
                    x=x,
                    y=side_sign * (inner + (recess + DOOR_PANEL_THICKNESS) / 2.0),
                    z=base_z + door_h + lintel_h / 2.0,
                ),
                material=cfg.material("concrete"),
                tags=("wall",),
            )
        )

    add_threshold(scene, cfg, params, geo, side_sign, prefix, index, x, base_z)


def add_threshold(
    scene: Scene,
    cfg: EnvConfig,
    params: EnvParams,
    geo: CorridorGeometry,
    side_sign: int,
    prefix: str,
    index: int,
    x: float,
    base_z: float,
) -> None:
    """세대문 앞 문턱. 명세 §8 - 주행 성패를 직접 가르는 요소.

    높이는 반드시 params 에서 읽는다. yaml 기본값을 직접 읽으면
    --threshold 오버라이드가 조용히 무시된다.
    """
    height = params.threshold_height
    if height <= 0.0:
        return
    depth = float(cfg.get("common.threshold.depth"))
    door_w = float(cfg.get("common.door.width"))
    recess = float(cfg.get("common.door.recess_depth"))
    # 우묵이 입구에 걸치도록 배치한다.
    y_center = side_sign * (geo.half_width + recess / 2.0)
    scene.add(
        Element(
            name=f"{prefix}_threshold{index}",
            geometry=Box((door_w, depth, height)),
            pose=Pose(x=x, y=y_center, z=base_z + height / 2.0),
            material=cfg.material("metal"),
            tags=("threshold",),
        )
    )


def add_parapet(scene: Scene, cfg: EnvConfig, geo: CorridorGeometry, side_sign: int) -> None:
    """편복도 개방측 난간.

    LiDAR 관점에서 중요하다. 난간 높이가 스캔면보다 높으면 벽처럼 보이고,
    낮으면 그쪽 방향의 반사가 사라져 정합(localization) 난이도가 올라간다.
    """
    height = float(cfg.get("common.parapet.height"))
    thickness = float(cfg.get("common.parapet.thickness"))
    scene.add(
        Element(
            name="parapet",
            geometry=Box((geo.length, thickness, height)),
            pose=Pose(
                x=geo.length / 2.0,
                y=side_sign * (geo.half_width + thickness / 2.0),
                z=height / 2.0,
            ),
            material=cfg.material("concrete"),
            tags=("wall", "parapet"),
        )
    )


def add_end_caps(scene: Scene, cfg: EnvConfig, params: EnvParams, geo: CorridorGeometry) -> None:
    """복도 양 끝단 마감. 먼 쪽은 방화문으로 둔다 (명세 §2.2)."""
    mat = cfg.material("concrete")
    height = geo.wall_height + geo.ramp_rise
    span = geo.width + 2 * geo.wall_thickness
    t = geo.wall_thickness

    scene.add(
        Element(
            name="end_wall_near",
            geometry=Box((t, span, height)),
            pose=Pose(x=-t / 2.0, y=0.0, z=height / 2.0),
            material=mat,
            tags=("wall",),
        )
    )
    add_fire_door(
        scene,
        cfg,
        params,
        name="fire_door_far",
        x=geo.length + t / 2.0,
        y=0.0,
        span=span,
        thickness=t,
        height=height,
        base_z=geo.floor_top_at(geo.length),
        axis="x",
    )


def add_fire_door(
    scene: Scene,
    cfg: EnvConfig,
    params: EnvParams,
    *,
    name: str,
    x: float,
    y: float,
    span: float,
    thickness: float,
    height: float,
    base_z: float,
    axis: str,
) -> None:
    """방화문. 상시 열림/닫힘 두 상태를 인자로 전환한다 (명세 §2.2).

    닫힘이면 개구부를 막는 문짝이 생기고, 열림이면 문짝이 벽에 붙어 접힌 상태로
    개구부가 비어 있어 로봇이 통과할 수 있다.
    """
    door_w = float(cfg.get("common.door.width"))
    mat_wall = cfg.material("concrete")
    mat_door = cfg.material("metal")

    side = (span - door_w) / 2.0
    for i, offset in enumerate((-(door_w / 2.0 + side / 2.0), door_w / 2.0 + side / 2.0)):
        if side <= 1e-6:
            continue
        pose = (
            Pose(x=x, y=y + offset, z=height / 2.0)
            if axis == "x"
            else Pose(x=x + offset, y=y, z=height / 2.0)
        )
        size = (thickness, side, height) if axis == "x" else (side, thickness, height)
        scene.add(
            Element(
                name=f"{name}_jamb{i}",
                geometry=Box(size),
                pose=pose,
                material=mat_wall,
                tags=("wall",),
            )
        )

    if params.fire_door_closed:
        size = (
            (thickness, door_w, height - base_z)
            if axis == "x"
            else (door_w, thickness, height - base_z)
        )
        pose = Pose(x=x, y=y, z=base_z + (height - base_z) / 2.0)
        scene.add(
            Element(
                name=f"{name}_panel",
                geometry=Box(size),
                pose=pose,
                material=mat_door,
                tags=("fire_door", "door"),
            )
        )
    else:
        # 열림 상태: 문짝이 한쪽 문설주에 경첩으로 90도 열려 안쪽(-축 방향) 벽면에 붙는다.
        # 개구부 자체는 비어 있어 로봇이 통과할 수 있고, 문짝이 유효폭을 leaf_t 만큼만 잠식한다.
        leaf_t = DOOR_PANEL_THICKNESS * 2
        leaf_h = height - base_z
        leaf_z = base_z + leaf_h / 2.0
        hinge_offset = door_w / 2.0 - leaf_t / 2.0
        if axis == "x":
            size = (door_w, leaf_t, leaf_h)
            pose = Pose(x=x - thickness / 2.0 - door_w / 2.0, y=y + hinge_offset, z=leaf_z)
        else:
            size = (leaf_t, door_w, leaf_h)
            pose = Pose(x=x + hinge_offset, y=y - thickness / 2.0 - door_w / 2.0, z=leaf_z)
        scene.add(
            Element(
                name=f"{name}_leaf_open",
                geometry=Box(size),
                pose=pose,
                material=mat_door,
                tags=("fire_door", "door"),
            )
        )


# --------------------------------------------------------------- 부착 장애물
def add_hydrant_box(
    scene: Scene,
    cfg: EnvConfig,
    geo: CorridorGeometry,
    side_sign: int,
    x: float,
    name: str = "hydrant_box",
) -> None:
    """옥내소화전함. 복도 유효폭을 실질적으로 잠식하는 핵심 장애물."""
    w = float(cfg.get("common.hydrant_box.width"))
    h = float(cfg.get("common.hydrant_box.height"))
    protrusion = float(cfg.get("common.hydrant_box.protrusion"))
    mount = float(cfg.get("common.hydrant_box.mount_height"))
    base_z = geo.floor_top_at(x)
    scene.add(
        Element(
            name=name,
            geometry=Box((w, protrusion, h)),
            pose=Pose(
                x=x,
                y=side_sign * (geo.half_width - protrusion / 2.0),
                z=base_z + mount + h / 2.0,
            ),
            material=cfg.material("metal"),
            tags=("obstacle", "hydrant"),
        )
    )


def add_milk_box(
    scene: Scene,
    cfg: EnvConfig,
    geo: CorridorGeometry,
    side_sign: int,
    index: int,
    x: float,
) -> None:
    """세대문 옆 우유함. 설치 높이가 LiDAR 스캔면보다 위면 주행에는 무관하다."""
    size = [float(v) for v in cfg.get("common.milk_box.size")]
    mount = float(cfg.get("common.milk_box.mount_height"))
    door_w = float(cfg.get("common.door.width"))
    base_z = geo.floor_top_at(x)
    scene.add(
        Element(
            name=f"milk_box{index}",
            geometry=Box((size[0], size[1], size[2])),
            pose=Pose(
                x=x + door_w / 2.0 + size[0] / 2.0,
                y=side_sign * (geo.half_width - size[1] / 2.0),
                z=base_z + mount + size[2] / 2.0,
            ),
            material=cfg.material("metal"),
            tags=("obstacle", "milk_box"),
        )
    )


def add_clutter(
    scene: Scene,
    cfg: EnvConfig,
    params: EnvParams,
    geo: CorridorGeometry,
    anchors: list[tuple[float, int]],
) -> int:
    """세대 앞 적치물을 시드 기반으로 배치한다.

    같은 seed면 같은 배치가 나와야 Phase 3 매트릭스 실험을 재현할 수 있다.
    anchors 는 (x, side_sign) 목록 - 보통 세대문 위치.
    """
    if not params.include_clutter or params.obstacle_density <= 0.0:
        return 0

    items = cfg.node("clutter.items")
    names = sorted(items.keys())
    rng = random.Random(params.seed)
    placed = 0

    for i, (x, side_sign) in enumerate(anchors):
        if rng.random() >= params.obstacle_density:
            continue
        kind = names[rng.randrange(len(names))]
        size = [float(v) for v in items[kind]["size"]]
        yaw = rng.uniform(-math.pi / 6.0, math.pi / 6.0)
        # 회전한 박스의 y방향 반폭. 이걸 빼지 않으면 긴 물건(자전거)이 벽을 뚫는다.
        half_y = (abs(size[0] * math.sin(yaw)) + abs(size[1] * math.cos(yaw))) / 2.0
        # 벽에 붙여 두되 복도 안쪽으로 조금 삐져나오게 한다.
        y = side_sign * (geo.half_width - half_y - rng.uniform(0.0, 0.15))
        x_off = x + rng.uniform(-0.6, 0.6)
        base_z = geo.floor_top_at(x_off)
        scene.add(
            Element(
                name=f"clutter{i}_{kind}",
                geometry=Box((size[0], size[1], size[2])),
                pose=Pose(x=x_off, y=y, z=base_z + size[2] / 2.0, yaw=yaw),
                material=cfg.material("obstacle"),
                static=True,
                tags=("obstacle", "clutter", kind),
            )
        )
        placed += 1
    return placed


def add_pillar(
    scene: Scene,
    cfg: EnvConfig,
    name: str,
    x: float,
    y: float,
    radius: float,
    height: float,
) -> None:
    scene.add(
        Element(
            name=name,
            geometry=Cylinder(radius=radius, length=height),
            pose=Pose(x=x, y=y, z=height / 2.0),
            material=cfg.material("concrete"),
            tags=("wall", "pillar"),
        )
    )
