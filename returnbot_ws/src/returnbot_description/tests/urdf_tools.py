"""URDF 렌더링 + 순기구학 헬퍼 (테스트 전용).

xacro 렌더는 `$(find returnbot_description)` 를 소스 트리 경로로 치환해서 돌린다.
ament 인덱스에 패키지가 설치되지 않은 상태(=아직 colcon build 전)에서도
검증이 가능해야 하기 때문이다.
"""

from __future__ import annotations

import math
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import xacro

# xacro.parse 는 `open(filename)` 을 로케일 인코딩으로 연다. 한국어 Windows(cp949)
# 에서는 xacro 파일 주석의 한글이 디코딩에서 깨진다. 파일을 UTF-8로 직접 읽어
# 문자열로 넘기면(xacro.parse 는 문자열이면 parseString 을 쓴다) 로케일과 무관해진다.
# 리눅스(UTF-8 로케일)에서는 동작이 동일하다.
_ORIGINAL_XACRO_PARSE = xacro.parse


def _parse_as_utf8(inp=None, filename=None):
    if inp is None and filename is not None:
        inp = Path(filename).read_text(encoding="utf-8")
    return _ORIGINAL_XACRO_PARSE(inp, filename)


xacro.parse = _parse_as_utf8

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TOP_XACRO = PACKAGE_ROOT / "urdf" / "returnbot.urdf.xacro"
FIND_TOKEN = "$(find returnbot_description)"


def render(**mappings) -> ET.Element:
    """xacro를 렌더해 URDF 루트 엘리먼트를 돌려준다."""
    text = TOP_XACRO.read_text(encoding="utf-8").replace(FIND_TOKEN, PACKAGE_ROOT.as_posix())
    tmp_dir = Path(tempfile.mkdtemp(prefix="returnbot_urdf_"))
    tmp = tmp_dir / "returnbot.urdf.xacro"
    tmp.write_text(text, encoding="utf-8")
    doc = xacro.process_file(str(tmp), mappings={k: str(v) for k, v in mappings.items()})
    return ET.fromstring(doc.toxml())


# ------------------------------------------------------------------- 변환 유틸
def rpy_matrix(roll: float, pitch: float, yaw: float) -> list[list[float]]:
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_vec(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def read_origin(node: ET.Element | None) -> tuple[list[float], list[float]]:
    if node is None:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    origin = node if node.tag == "origin" else node.find("origin")
    if origin is None:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    xyz = [float(v) for v in (origin.get("xyz") or "0 0 0").split()]
    rpy = [float(v) for v in (origin.get("rpy") or "0 0 0").split()]
    return xyz, rpy


# --------------------------------------------------------------------- 트리
class UrdfTree:
    """조인트 그래프와 링크 원점 순기구학."""

    def __init__(self, root: ET.Element) -> None:
        self.root = root
        self.links = {l.get("name"): l for l in root.findall("link")}
        self.joints = root.findall("joint")
        self.parent_of: dict[str, tuple[str, ET.Element]] = {}
        for joint in self.joints:
            child = joint.find("child").get("link")
            parent = joint.find("parent").get("link")
            if child in self.parent_of:
                raise ValueError(f"링크 {child} 에 부모가 둘 이상이다 (URDF는 트리여야 한다)")
            self.parent_of[child] = (parent, joint)

    @property
    def base(self) -> str:
        roots = [name for name in self.links if name not in self.parent_of]
        if len(roots) != 1:
            raise ValueError(f"루트 링크가 하나가 아니다: {roots}")
        return roots[0]

    def chain(self, link: str) -> list[ET.Element]:
        """base → link 까지의 조인트 목록. 순환이면 예외."""
        out: list[ET.Element] = []
        seen = {link}
        cursor = link
        while cursor in self.parent_of:
            parent, joint = self.parent_of[cursor]
            out.append(joint)
            if parent in seen:
                raise ValueError(f"조인트 그래프에 순환이 있다: {parent}")
            seen.add(parent)
            cursor = parent
        return list(reversed(out))

    def link_pose(self, link: str) -> tuple[list[float], list[list[float]]]:
        """base 프레임에서 본 링크 원점의 위치와 회전 (모든 조인트 각도 0)."""
        pos = [0.0, 0.0, 0.0]
        rot = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        for joint in self.chain(link):
            xyz, rpy = read_origin(joint)
            pos = [pos[i] + mat_vec(rot, xyz)[i] for i in range(3)]
            rot = mat_mul(rot, rpy_matrix(*rpy))
        return pos, rot

    def center_of_mass(self) -> tuple[float, list[float]]:
        """(총질량, base 프레임 질량중심). 링크 로컬 inertial origin까지 반영한다."""
        total = 0.0
        moment = [0.0, 0.0, 0.0]
        for name, link in self.links.items():
            inertial = link.find("inertial")
            if inertial is None:
                continue
            mass = float(inertial.find("mass").get("value"))
            local_xyz, _ = read_origin(inertial)
            pos, rot = self.link_pose(name)
            world = [pos[i] + mat_vec(rot, local_xyz)[i] for i in range(3)]
            total += mass
            moment = [moment[i] + mass * world[i] for i in range(3)]
        if total <= 0:
            raise ValueError("총질량이 0이다")
        return total, [m / total for m in moment]
