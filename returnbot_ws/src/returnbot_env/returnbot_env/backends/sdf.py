"""IR → Gazebo SDF 월드.

표준 라이브러리(xml.etree)만 쓴다. 명세 §2.3에 따라 Phase 0~3은 텍스처 없이
콜리전 정확도를 우선하므로 visual은 단색 material로만 채운다.

Gazebo 버전 주의 (docs/env_reference.md §6):
    명세 §4는 `gz sim` 표기지만 ROS 2 Humble의 tier-1 페어링은 Fortress(`ign gazebo`)다.
    시스템 플러그인 이름이 둘 사이에 다르므로 flavor 인자로 전환한다.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Literal

from ..ir import Box, Cylinder, Element, Scene

Flavor = Literal["fortress", "harmonic"]

#: 시스템 플러그인 이름 표. Fortress = ignition::, Harmonic = gz::
_PLUGIN_TABLE: dict[str, dict[str, tuple[str, str]]] = {
    "fortress": {
        "physics": ("ignition-gazebo-physics-system", "ignition::gazebo::systems::Physics"),
        "user_commands": (
            "ignition-gazebo-user-commands-system",
            "ignition::gazebo::systems::UserCommands",
        ),
        "scene_broadcaster": (
            "ignition-gazebo-scene-broadcaster-system",
            "ignition::gazebo::systems::SceneBroadcaster",
        ),
        "sensors": ("ignition-gazebo-sensors-system", "ignition::gazebo::systems::Sensors"),
        "imu": ("ignition-gazebo-imu-system", "ignition::gazebo::systems::Imu"),
        "contact": ("ignition-gazebo-contact-system", "ignition::gazebo::systems::Contact"),
    },
    "harmonic": {
        "physics": ("gz-sim-physics-system", "gz::sim::systems::Physics"),
        "user_commands": ("gz-sim-user-commands-system", "gz::sim::systems::UserCommands"),
        "scene_broadcaster": (
            "gz-sim-scene-broadcaster-system",
            "gz::sim::systems::SceneBroadcaster",
        ),
        "sensors": ("gz-sim-sensors-system", "gz::sim::systems::Sensors"),
        "imu": ("gz-sim-imu-system", "gz::sim::systems::Imu"),
        "contact": ("gz-sim-contact-system", "gz::sim::systems::Contact"),
    },
}

SDF_VERSION = "1.9"
#: 물리 스텝. Phase 2에서 문턱 충격을 보려면 충분히 작아야 한다.
MAX_STEP_SIZE = 0.001


def to_sdf(scene: Scene, flavor: Flavor = "fortress") -> str:
    if flavor not in _PLUGIN_TABLE:
        raise ValueError(f"알 수 없는 Gazebo flavor: {flavor} (가능: {list(_PLUGIN_TABLE)})")

    sdf = ET.Element("sdf", {"version": SDF_VERSION})
    world = ET.SubElement(sdf, "world", {"name": scene.name})

    _add_physics(world, flavor)
    _add_scene_and_light(world)

    for element in scene:
        _add_model(world, element)

    tree = ET.ElementTree(sdf)
    ET.indent(tree, space="  ")
    body = ET.tostring(sdf, encoding="unicode")

    header = _header_comment(scene, flavor)
    return f'<?xml version="1.0" ?>\n{header}{body}\n'


def _header_comment(scene: Scene, flavor: Flavor) -> str:
    meta = json.dumps(scene.metadata, ensure_ascii=False, indent=2, default=str)
    body = (
        "  returnbot_env 자동 생성 파일 — 직접 수정하지 말 것.\n"
        "  재생성: python -m returnbot_env.cli --type <A|B|C> ...\n"
        f"  Gazebo flavor: {flavor}\n"
        f"  생성 인자:\n{meta}\n"
    )
    return f"<!--\n{_comment_safe(body)}-->\n"


def _comment_safe(text: str) -> str:
    """XML 주석은 '- -'(붙여쓴 두 하이픈)를 담을 수 없고 '-'로 끝날 수도 없다."""
    while "--" in text:
        text = text.replace("--", "- -")
    return text if not text.endswith("-") else text + " "


def _add_physics(world: ET.Element, flavor: Flavor) -> None:
    physics = ET.SubElement(world, "physics", {"name": "default", "type": "ode"})
    ET.SubElement(physics, "max_step_size").text = str(MAX_STEP_SIZE)
    ET.SubElement(physics, "real_time_factor").text = "1.0"

    table = _PLUGIN_TABLE[flavor]
    for key in ("physics", "user_commands", "scene_broadcaster", "sensors", "imu", "contact"):
        filename, name = table[key]
        plugin = ET.SubElement(world, "plugin", {"filename": filename, "name": name})
        if key == "sensors":
            ET.SubElement(plugin, "render_engine").text = "ogre2"


def _add_scene_and_light(world: ET.Element) -> None:
    ET.SubElement(world, "gravity").text = "0 0 -9.8"

    scene_el = ET.SubElement(world, "scene")
    ET.SubElement(scene_el, "ambient").text = "0.5 0.5 0.5 1"
    ET.SubElement(scene_el, "background").text = "0.75 0.8 0.85 1"
    ET.SubElement(scene_el, "shadows").text = "true"

    # 주간 자연광. 야간 복도등·센서등은 Phase 4 카메라 검증에서 추가한다 (명세 §2.2).
    light = ET.SubElement(world, "light", {"type": "directional", "name": "daylight"})
    ET.SubElement(light, "cast_shadows").text = "true"
    ET.SubElement(light, "pose").text = "0 0 10 0 0 0"
    ET.SubElement(light, "diffuse").text = "0.9 0.9 0.85 1"
    ET.SubElement(light, "specular").text = "0.2 0.2 0.2 1"
    ET.SubElement(light, "direction").text = "-0.4 0.3 -0.9"


def _add_model(world: ET.Element, element: Element) -> None:
    model = ET.SubElement(world, "model", {"name": element.name})
    ET.SubElement(model, "static").text = "true" if element.static else "false"
    ET.SubElement(model, "pose").text = _pose_text(element)

    link = ET.SubElement(model, "link", {"name": "link"})

    if element.collision:
        collision = ET.SubElement(link, "collision", {"name": "collision"})
        _add_geometry(collision, element)
        surface = ET.SubElement(collision, "surface")
        friction = ET.SubElement(surface, "friction")
        ode = ET.SubElement(friction, "ode")
        ET.SubElement(ode, "mu").text = str(element.material.mu)
        ET.SubElement(ode, "mu2").text = str(element.material.mu2)

    visual = ET.SubElement(link, "visual", {"name": "visual"})
    _add_geometry(visual, element)
    material = ET.SubElement(visual, "material")
    rgba = " ".join(str(c) for c in element.material.rgba)
    ET.SubElement(material, "ambient").text = rgba
    ET.SubElement(material, "diffuse").text = rgba
    ET.SubElement(material, "specular").text = "0.1 0.1 0.1 1"


def _add_geometry(parent: ET.Element, element: Element) -> None:
    geometry = ET.SubElement(parent, "geometry")
    geom = element.geometry
    if isinstance(geom, Box):
        box = ET.SubElement(geometry, "box")
        ET.SubElement(box, "size").text = " ".join(f"{v:.6g}" for v in geom.size)
    elif isinstance(geom, Cylinder):
        cylinder = ET.SubElement(geometry, "cylinder")
        ET.SubElement(cylinder, "radius").text = f"{geom.radius:.6g}"
        ET.SubElement(cylinder, "length").text = f"{geom.length:.6g}"
    else:  # pragma: no cover - Geometry 유니온이 늘어나면 여기서 걸린다
        raise TypeError(f"SDF 백엔드가 모르는 지오메트리: {type(geom).__name__}")


def _pose_text(element: Element) -> str:
    return " ".join(f"{v:.6g}" for v in element.pose.as_tuple())
