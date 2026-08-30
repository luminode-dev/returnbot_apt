"""월드 생성 인자.

기본값은 전부 env_types.yaml에서 오고, CLI 인자가 그 위에 덮어쓴다.
코드에 치수 리터럴을 두지 않는다 (명세 §7).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .config import EnvConfig

APARTMENT_TYPES = ("A", "B", "C")


@dataclass
class EnvParams:
    apt_type: str
    label: str

    #: 유형 A/B(복도형)에서만 의미 있는 값
    corridor_width: float = 0.0
    corridor_length: float = 0.0
    #: 유형 C(홀형)에서만 의미 있는 값
    hall_width: float = 0.0
    hall_depth: float = 0.0
    elevator_count: int = 0

    unit_count: int = 0
    door_side: str = "+y"
    open_side: str | None = None
    floor_material: str = "corridor_tile"

    threshold_height: float = 0.0
    ramp_grade: float = 0.0
    ramp_rise: float = 0.0
    elevator_door_width: float = 0.0

    obstacle_density: float = 0.0
    include_clutter: bool = True
    #: 방화문 상시 열림/닫힘 두 상태 (명세 §2.2)
    fire_door_closed: bool = False
    seed: int = 0

    #: 생성 산출물 주석/리포트에 그대로 실린다.
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def ramp_length(self) -> float:
        """경사로 수평 길이 = 단차 / 구배. 구배가 0이면 경사로 없음."""
        if self.ramp_grade <= 0.0:
            return 0.0
        return self.ramp_rise / self.ramp_grade

    @property
    def is_hall(self) -> bool:
        return self.apt_type == "C"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ramp_length"] = round(self.ramp_length, 4)
        return data


def build_params(cfg: EnvConfig, apt_type: str, **overrides: Any) -> EnvParams:
    """yaml 기본값으로 EnvParams를 만들고, None이 아닌 override만 덮어쓴다."""
    apt_type = apt_type.upper()
    if apt_type not in APARTMENT_TYPES:
        raise ValueError(f"알 수 없는 아파트 유형: {apt_type} (가능: {APARTMENT_TYPES})")

    t = f"types.{apt_type}"
    params = EnvParams(
        apt_type=apt_type,
        label=cfg.get(f"{t}.label"),
        unit_count=int(cfg.get(f"{t}.unit_count")),
        floor_material=cfg.get(f"{t}.floor_material"),
        threshold_height=float(cfg.get("common.threshold.height")),
        ramp_grade=float(cfg.get("common.ramp.grade")),
        ramp_rise=float(cfg.get("common.ramp.rise")),
        elevator_door_width=float(cfg.get("common.elevator.door_width")),
        obstacle_density=float(cfg.get("clutter.density")),
    )

    if apt_type == "C":
        params.hall_width = float(cfg.get(f"{t}.hall_width"))
        params.hall_depth = float(cfg.get(f"{t}.hall_depth"))
        params.elevator_count = int(cfg.get(f"{t}.elevator_count"))
        params.door_side = "hall"
    else:
        params.corridor_width = float(cfg.get(f"{t}.corridor_width"))
        params.corridor_length = float(cfg.get(f"{t}.corridor_length"))
        params.door_side = cfg.get(f"{t}.door_side")
        params.open_side = cfg.get(f"{t}.open_side")

    for key, value in overrides.items():
        if value is None:
            continue
        if not hasattr(params, key):
            raise AttributeError(f"EnvParams 에 없는 인자: {key}")
        setattr(params, key, value)

    _validate(params)
    return params


def _validate(params: EnvParams) -> None:
    if params.is_hall:
        if params.hall_width <= 0 or params.hall_depth <= 0:
            raise ValueError("홀형(C)은 hall_width/hall_depth 가 양수여야 한다")
    else:
        if params.corridor_width <= 0:
            raise ValueError("corridor_width 는 양수여야 한다")
        if params.corridor_length <= 0:
            raise ValueError("corridor_length 는 양수여야 한다")
    if params.unit_count < 1:
        raise ValueError("unit_count 는 1 이상이어야 한다")
    if not 0.0 <= params.obstacle_density <= 1.0:
        raise ValueError("obstacle_density 는 0..1 범위여야 한다")
    if params.threshold_height < 0:
        raise ValueError("threshold_height 는 음수일 수 없다")
