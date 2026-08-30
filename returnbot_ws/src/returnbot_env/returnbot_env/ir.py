"""월드의 중립 중간표현(IR).

백엔드(SDF / USD / SVG)는 모두 이 IR만 소비한다. 명세 §6의
"Gazebo world(sdf)와 USD를 동일 소스에서 생성" 요구를 이 한 겹으로 만족시킨다.

좌표계 (전 백엔드 공통):
    X = 복도 길이축 (로봇 주행 방향, 원점이 복도 시작단)
    Y = 복도 폭축 (복도 중심선이 y=0)
    Z = 상방 (기준 바닥면이 z=0)
회전은 SDF와 동일한 RPY(고정축 X-Y-Z, R = Rz·Ry·Rx) 규약을 쓴다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Sequence


@dataclass(frozen=True)
class Pose:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (self.x, self.y, self.z, self.roll, self.pitch, self.yaw)

    def rotation_matrix(self) -> tuple[tuple[float, float, float], ...]:
        cr, sr = math.cos(self.roll), math.sin(self.roll)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        # R = Rz(yaw) * Ry(pitch) * Rx(roll)
        return (
            (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
            (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
            (-sp, cp * sr, cp * cr),
        )


@dataclass(frozen=True)
class Material:
    """재질. 마찰계수는 전부 튜닝 시작점이다 (명세 §8)."""

    name: str
    mu: float
    mu2: float
    rgba: tuple[float, float, float, float]


@dataclass(frozen=True)
class Box:
    size: tuple[float, float, float]


@dataclass(frozen=True)
class Cylinder:
    radius: float
    length: float


Geometry = Box | Cylinder


@dataclass(frozen=True)
class Element:
    """월드를 구성하는 단위 지오메트리 하나."""

    name: str
    geometry: Geometry
    pose: Pose
    material: Material
    static: bool = True
    collision: bool = True
    #: 백엔드·테스트가 요소를 분류할 때 쓰는 라벨 ('wall', 'door', 'threshold', ...)
    tags: tuple[str, ...] = ()

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags

    def footprint(self) -> list[tuple[float, float]]:
        """탑뷰 XY 투영 외곽선. SVG 렌더러와 치수 검증 테스트가 쓴다."""
        if isinstance(self.geometry, Cylinder):
            # 기둥은 항상 직립으로만 쓰므로 원을 다각형으로 근사한다.
            n = 24
            r = self.geometry.radius
            return [
                (
                    self.pose.x + r * math.cos(2 * math.pi * i / n),
                    self.pose.y + r * math.sin(2 * math.pi * i / n),
                )
                for i in range(n)
            ]

        hx, hy, hz = (s / 2.0 for s in self.geometry.size)
        rot = self.pose.rotation_matrix()
        projected: list[tuple[float, float]] = []
        for sx in (-hx, hx):
            for sy in (-hy, hy):
                for sz in (-hz, hz):
                    wx = rot[0][0] * sx + rot[0][1] * sy + rot[0][2] * sz + self.pose.x
                    wy = rot[1][0] * sx + rot[1][1] * sy + rot[1][2] * sz + self.pose.y
                    projected.append((wx, wy))
        return convex_hull(projected)


@dataclass
class Scene:
    """월드 하나. 백엔드가 소비하는 유일한 입력."""

    name: str
    elements: list[Element] = field(default_factory=list)
    #: 생성 인자 원본. 백엔드 주석과 검증 테스트가 참조한다.
    metadata: dict = field(default_factory=dict)

    def add(self, element: Element) -> Element:
        if any(e.name == element.name for e in self.elements):
            raise ValueError(f"중복된 요소 이름: {element.name}")
        self.elements.append(element)
        return element

    def extend(self, elements: Iterable[Element]) -> None:
        for element in elements:
            self.add(element)

    def by_tag(self, tag: str) -> list[Element]:
        return [e for e in self.elements if e.has_tag(tag)]

    def __iter__(self) -> Iterator[Element]:
        return iter(self.elements)

    def __len__(self) -> int:
        return len(self.elements)

    def bounds_2d(self) -> tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y). 빈 씬이면 0 크기 박스."""
        points = [p for e in self.elements for p in e.footprint()]
        if not points:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return (min(xs), min(ys), max(xs), max(ys))


def convex_hull(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """단조 체인 볼록껍질. 박스 8꼭짓점 투영에만 쓰므로 규모가 작다."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return list(pts)

    def cross(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(seq) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for p in seq:
            while len(out) >= 2 and cross(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out

    lower = half(pts)
    upper = half(reversed(pts))
    return lower[:-1] + upper[:-1]
