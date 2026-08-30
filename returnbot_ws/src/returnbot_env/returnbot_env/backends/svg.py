"""IR → 탑뷰 평면도 SVG.

Phase 0 완료 기준의 "스크린샷" 대체물이다. Gazebo 없이도 생성 결과를 눈으로
검증할 수 있고, 치수 주기가 들어가므로 Gazebo가 준비된 뒤에도 계속 쓸모가 있다.
외부 의존성 없음.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from ..ir import Scene

#: 태그별 채움색. 앞에 있는 태그가 우선한다.
_TAG_STYLE: list[tuple[str, str, str]] = [
    # (tag, fill, stroke)
    ("clutter", "#c94f4f", "#8c2f2f"),
    ("hydrant", "#e08a1e", "#a45f0d"),
    ("milk_box", "#d8b34a", "#9c7f22"),
    ("elevator_door", "#3f7fbf", "#25547f"),
    ("fire_door", "#8b5fbf", "#5d3b85"),
    ("door", "#7a5230", "#4d3218"),
    ("threshold", "#8f8f96", "#5c5c62"),
    ("pillar", "#6d6d74", "#3f3f45"),
    ("parapet", "#a9b0b8", "#6f767e"),
    ("wall", "#5a5f66", "#33373c"),
    ("ramp", "#cfd6c2", "#9aa38a"),
    ("floor", "#eceae4", "#cfccc4"),
]

_DEFAULT_STYLE = ("#b0b0b0", "#707070")

MARGIN_PX = 70
PX_PER_M = 55.0


def to_svg(scene: Scene, px_per_m: float = PX_PER_M) -> str:
    min_x, min_y, max_x, max_y = scene.bounds_2d()
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    width_px = span_x * px_per_m + 2 * MARGIN_PX
    height_px = span_y * px_per_m + 2 * MARGIN_PX + 90  # 하단 범례 공간

    def sx(x: float) -> float:
        return MARGIN_PX + (x - min_x) * px_per_m

    def sy(y: float) -> float:
        # SVG는 y가 아래로 증가하므로 뒤집는다.
        return MARGIN_PX + (max_y - y) * px_per_m

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px:.0f}" '
        f'height="{height_px:.0f}" viewBox="0 0 {width_px:.0f} {height_px:.0f}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        "<style>text{font-family:'DejaVu Sans',sans-serif}</style>",
    ]

    # 요소는 floor → wall → 나머지 순으로 그려 겹침을 자연스럽게 한다.
    ordered = sorted(scene.elements, key=lambda e: -_z_order(e.tags))
    for element in ordered:
        fill, stroke = _style_for(element.tags)
        pts = " ".join(f"{sx(px):.2f},{sy(py):.2f}" for px, py in element.footprint())
        parts.append(
            f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="0.8" fill-opacity="0.9"><title>{escape(element.name)}</title></polygon>'
        )

    parts.extend(_annotations(scene, sx, sy, min_x, min_y, max_x, max_y, px_per_m))
    parts.extend(_legend(scene, MARGIN_PX, height_px - 60))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _z_order(tags: tuple[str, ...]) -> int:
    for i, (tag, _f, _s) in enumerate(_TAG_STYLE):
        if tag in tags:
            return i
    return len(_TAG_STYLE)


def _style_for(tags: tuple[str, ...]) -> tuple[str, str]:
    for tag, fill, stroke in _TAG_STYLE:
        if tag in tags:
            return fill, stroke
    return _DEFAULT_STYLE


def _annotations(scene, sx, sy, min_x, min_y, max_x, max_y, px_per_m) -> list[str]:
    """제목, 유효폭 치수선, 축척 막대."""
    meta = scene.metadata
    derived = meta.get("derived", {})
    label = meta.get("label", scene.name)
    apt_type = meta.get("type", "?")

    out: list[str] = [
        f'<text x="{MARGIN_PX}" y="28" font-size="17" font-weight="600" fill="#222">'
        f"{escape(f'유형 {apt_type} — {label}')}</text>"
    ]

    if "corridor_clear_width" in derived:
        w = derived["corridor_clear_width"]
        subtitle = f"복도 유효폭 {w:.2f} m · 길이 {meta['params']['corridor_length']:.1f} m"
        # 유효폭 치수선: 복도 초입에 세로선으로 긋는다.
        x_dim = min_x + (max_x - min_x) * 0.08
        y0, y1 = -w / 2.0, w / 2.0
        out.append(
            f'<line x1="{sx(x_dim):.1f}" y1="{sy(y0):.1f}" x2="{sx(x_dim):.1f}" '
            f'y2="{sy(y1):.1f}" stroke="#c0392b" stroke-width="1.6"/>'
        )
        for yv in (y0, y1):
            out.append(
                f'<line x1="{sx(x_dim) - 6:.1f}" y1="{sy(yv):.1f}" '
                f'x2="{sx(x_dim) + 6:.1f}" y2="{sy(yv):.1f}" stroke="#c0392b" stroke-width="1.6"/>'
            )
        out.append(
            f'<text x="{sx(x_dim) + 9:.1f}" y="{sy(0.0):.1f}" font-size="13" '
            f'fill="#c0392b">{w:.2f} m</text>'
        )
    elif "hall_width" in derived:
        subtitle = f"홀 {derived['hall_width']:.2f} × {derived['hall_depth']:.2f} m"
    else:
        subtitle = ""

    if subtitle:
        out.append(
            f'<text x="{MARGIN_PX}" y="48" font-size="13" fill="#555">{escape(subtitle)}</text>'
        )

    rise = derived.get("ramp_rise", 0.0)
    if rise:
        x0, x1 = derived["ramp_x0"], derived["ramp_x1"]
        grade = meta["params"]["ramp_grade"]
        out.append(
            f'<text x="{sx((x0 + x1) / 2):.1f}" y="{sy(max_y) - 6:.1f}" font-size="12" '
            f'text-anchor="middle" fill="#5a6b3a">'
            f"{escape(f'경사로 {grade * 100:.0f}% · 단차 {rise * 1000:.0f} mm')}</text>"
        )

    # 축척 막대 1 m
    bar_x = sx(max_x) - px_per_m
    bar_y = sy(min_y) + 26
    out.append(
        f'<line x1="{bar_x:.1f}" y1="{bar_y:.1f}" x2="{bar_x + px_per_m:.1f}" '
        f'y2="{bar_y:.1f}" stroke="#222" stroke-width="2"/>'
    )
    out.append(
        f'<text x="{bar_x + px_per_m / 2:.1f}" y="{bar_y - 5:.1f}" font-size="11" '
        f'text-anchor="middle" fill="#222">1 m</text>'
    )
    return out


def _legend(scene: Scene, x: float, y: float) -> list[str]:
    present = {tag for e in scene for tag in e.tags}
    labels = {
        "wall": "벽",
        "parapet": "난간(개방측)",
        "door": "세대문",
        "elevator_door": "승강기문",
        "fire_door": "방화문",
        "threshold": "문턱",
        "ramp": "경사로",
        "hydrant": "소화전함",
        "milk_box": "우유함",
        "clutter": "적치물",
        "pillar": "기둥",
    }
    out: list[str] = []
    cx = x
    for tag, text in labels.items():
        if tag not in present:
            continue
        fill, stroke = _style_for((tag,))
        out.append(
            f'<rect x="{cx:.1f}" y="{y:.1f}" width="13" height="13" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="0.8"/>'
        )
        out.append(
            f'<text x="{cx + 18:.1f}" y="{y + 11:.1f}" font-size="12" fill="#333">'
            f"{escape(text)}</text>"
        )
        cx += 18 + len(text) * 13 + 16
    return out
