"""Phase 1 URDF 검증.

`check_urdf` 로 하는 검사(단일 루트, 순환 없음, 트리 무결성)를 여기서 순수 파이썬으로
수행한다. ROS 환경 없이도 돌기 때문에 WSL 구축 전에 설계 오류를 잡을 수 있다.
WSL 구축 후에는 `check_urdf` 와 RViz TF 확인으로 이중 검증한다.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest
import yaml

from urdf_tools import PACKAGE_ROOT, UrdfTree, read_origin, render

DIMENSIONS_YAML = PACKAGE_ROOT / "config" / "robot_dimensions.yaml"
PARAMS_XACRO = PACKAGE_ROOT / "urdf" / "robot_params.xacro"


@pytest.fixture(scope="module")
def urdf() -> ET.Element:
    return render()


@pytest.fixture(scope="module")
def tree(urdf) -> UrdfTree:
    return UrdfTree(urdf)


@pytest.fixture(scope="module")
def dims() -> dict:
    with open(DIMENSIONS_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def value(dims: dict, dotted: str):
    node = dims
    for key in dotted.split("."):
        node = node[key]
    return node["value"] if isinstance(node, dict) and "value" in node else node


# ------------------------------------------------------------------ 트리 무결성
def test_xacro가_렌더된다(urdf):
    assert urdf.tag == "robot"
    assert urdf.get("name") == "returnbot"


def test_루트가_base_footprint_하나다(tree):
    assert tree.base == "base_footprint"


def test_모든_링크가_트리에_연결되어_있다(tree):
    for name in tree.links:
        tree.chain(name)  # 순환이거나 끊겨 있으면 예외


def test_필수_프레임이_존재한다(tree):
    required = {
        "base_footprint",
        "base_link",
        "left_wheel_link",
        "right_wheel_link",
        "left_caster_link",
        "right_caster_link",
        "lidar_link",
        "imu_link",
        "camera_link",
        "camera_optical_link",
    }
    assert required <= set(tree.links)


def test_구동륜은_continuous_캐스터는_fixed다(urdf):
    types = {j.get("name"): j.get("type") for j in urdf.findall("joint")}
    assert types["left_wheel_joint"] == "continuous"
    assert types["right_wheel_joint"] == "continuous"
    # 스위블 근사 - casters.xacro 주석 참조. Phase 4에서 조인트 기반으로 상세화 검토
    assert types["left_caster_joint"] == "fixed"
    assert types["right_caster_joint"] == "fixed"


def test_구동륜_회전축이_링크_z축이다(urdf):
    """조인트 origin rpy 로 링크를 돌려 원기둥 축을 차량 y축에 맞춘 구조."""
    for name in ("left_wheel_joint", "right_wheel_joint"):
        joint = next(j for j in urdf.findall("joint") if j.get("name") == name)
        axis = [float(v) for v in joint.find("axis").get("xyz").split()]
        assert axis == [0.0, 0.0, 1.0]
        _, rpy = read_origin(joint)
        assert rpy[0] == pytest.approx(-math.pi / 2.0)


# ------------------------------------------------------------------ 접지 형상
def test_구동륜과_캐스터가_모두_지면에_닿는다(tree, dims):
    """하나라도 뜨면 Gazebo에서 로봇이 기울거나 튄다."""
    wheel_r = value(dims, "drive.wheel_radius")
    caster_r = value(dims, "caster.radius")
    for name in ("left_wheel_link", "right_wheel_link"):
        pos, _ = tree.link_pose(name)
        assert pos[2] == pytest.approx(wheel_r, abs=1e-9)
    for name in ("left_caster_link", "right_caster_link"):
        pos, _ = tree.link_pose(name)
        assert pos[2] == pytest.approx(caster_r, abs=1e-9)


def test_구동축이_base_link_원점에_있다(tree):
    """차동구동의 순간회전중심 = base_link 원점. odom 계산이 단순해진다."""
    for name in ("left_wheel_link", "right_wheel_link"):
        pos, _ = tree.link_pose(name)
        assert pos[0] == pytest.approx(0.0, abs=1e-12)


def test_캐스터가_후방에_있다(tree, dims):
    wheelbase = value(dims, "chassis.wheelbase")
    for name in ("left_caster_link", "right_caster_link"):
        pos, _ = tree.link_pose(name)
        assert pos[0] == pytest.approx(-wheelbase, abs=1e-9)


def test_lidar가_차체_최상면_위에_있다(tree, dims):
    """LD19 360도 시야 확보. 차체에 가리면 스캔에 사각이 생긴다."""
    body_top = value(dims, "body.height")
    pos, _ = tree.link_pose("lidar_link")
    lidar_h = value(dims, "sensors.lidar.size")[2]
    assert pos[2] - lidar_h / 2.0 >= body_top - 1e-9


def test_센서_링크에는_콜리전이_없다(urdf):
    """LiDAR 하우징에 콜리전을 두면 스캔이 통째로 죽는다.

    고정 조인트 링크는 SDF 변환에서 부모로 합쳐지므로, 광선이 자기 하우징
    (반경 0.03 m)을 먼저 때리고 range_min(0.05 m)으로 클램프된다.
    실제로 전 방향 0.05 m가 나오는 것을 Phase 2 브링업에서 확인했다.
    """
    for name in ("lidar_link", "imu_link", "camera_link", "camera_optical_link"):
        link = next(l for l in urdf.findall("link") if l.get("name") == name)
        assert link.find("collision") is None, f"{name} 에 콜리전이 있으면 안 된다"


def test_주행부에는_콜리전이_있다(urdf):
    """반대로 접지·충돌에 관여하는 링크는 반드시 콜리전이 있어야 한다."""
    for name in ("base_link", "left_wheel_link", "right_wheel_link",
                 "left_caster_link", "right_caster_link"):
        link = next(l for l in urdf.findall("link") if l.get("name") == name)
        assert link.find("collision") is not None, f"{name} 에 콜리전이 없다"


def test_카메라_광학프레임이_REP103을_따른다(tree):
    """apriltag_ros 등 vision 노드가 z 전방 / x 우측 / y 하방을 전제한다."""
    _, rot = tree.link_pose("camera_optical_link")
    forward = [rot[i][2] for i in range(3)]  # 광학 z축
    right = [rot[i][0] for i in range(3)]  # 광학 x축
    assert forward == pytest.approx([1.0, 0.0, 0.0], abs=1e-9)  # 차량 +x = 전방
    assert right == pytest.approx([0.0, -1.0, 0.0], abs=1e-9)  # 차량 -y = 우측


# ------------------------------------------------------------------ 질량·관성
def test_총질량이_명세와_일치한다(tree, dims):
    total, _ = tree.center_of_mass()
    assert total == pytest.approx(value(dims, "chassis.total_mass"), abs=1e-9)


@pytest.mark.parametrize("wheelbase", [0.35, 0.4, 0.5])
def test_무게배분이_60대40이다(dims, wheelbase):
    """명세 §3 구동축:캐스터 = 60:40.

    지지점이 구동축(x=0)과 캐스터축(x=-wheelbase) 두 곳이므로 캐스터 하중비는
    전체 질량중심의 x 위치로 결정된다. 전방 카메라처럼 오프셋을 가진 부품을
    빠뜨리면 이 값이 조용히 틀어진다.
    """
    tree = UrdfTree(render(wheelbase=wheelbase))
    total, com = tree.center_of_mass()
    caster_ratio = abs(com[0]) / wheelbase
    expected = 1.0 - value(dims, "chassis.drive_load_ratio")
    assert caster_ratio == pytest.approx(expected, abs=1e-9)


def test_질량중심이_좌우_대칭이다(tree):
    _, com = tree.center_of_mass()
    assert com[1] == pytest.approx(0.0, abs=1e-12)


def test_모든_관성이_물리적으로_타당하다(urdf):
    """양수이고 주모멘트가 삼각부등식을 만족해야 한다. 위반하면 솔버가 발산한다."""
    for link in urdf.findall("link"):
        inertial = link.find("inertial")
        if inertial is None:
            continue
        name = link.get("name")
        mass = float(inertial.find("mass").get("value"))
        assert mass > 0, f"{name} 질량이 0 이하"
        inertia = inertial.find("inertia")
        ixx = float(inertia.get("ixx"))
        iyy = float(inertia.get("iyy"))
        izz = float(inertia.get("izz"))
        assert min(ixx, iyy, izz) > 0, f"{name} 관성모멘트가 0 이하"
        assert ixx + iyy >= izz - 1e-12, f"{name} 삼각부등식 위반"
        assert iyy + izz >= ixx - 1e-12, f"{name} 삼각부등식 위반"
        assert izz + ixx >= iyy - 1e-12, f"{name} 삼각부등식 위반"


def test_차체_관성이_박스_공식과_일치한다(urdf, dims):
    """매크로가 실제로 치수에서 계산하고 있는지 (상수 하드코딩이 아닌지) 확인."""
    link = next(l for l in urdf.findall("link") if l.get("name") == "base_link")
    inertial = link.find("inertial")
    mass = float(inertial.find("mass").get("value"))
    x = value(dims, "body.depth")
    y = value(dims, "body.width")
    z = value(dims, "body.height") - value(dims, "body.ground_clearance")
    inertia = inertial.find("inertia")
    assert float(inertia.get("ixx")) == pytest.approx(mass * (y * y + z * z) / 12.0)
    assert float(inertia.get("iyy")) == pytest.approx(mass * (x * x + z * z) / 12.0)
    assert float(inertia.get("izz")) == pytest.approx(mass * (x * x + y * y) / 12.0)


def test_구동륜_관성이_원기둥_공식과_일치한다(urdf, dims):
    link = next(l for l in urdf.findall("link") if l.get("name") == "left_wheel_link")
    inertial = link.find("inertial")
    mass = float(inertial.find("mass").get("value"))
    r = value(dims, "drive.wheel_radius")
    h = value(dims, "drive.wheel_width")
    inertia = inertial.find("inertia")
    assert float(inertia.get("izz")) == pytest.approx(mass * r * r / 2.0)
    assert float(inertia.get("ixx")) == pytest.approx(mass * (3 * r * r + h * h) / 12.0)


# ------------------------------------------------------------------ 인자 노출
@pytest.mark.parametrize("body_width", [0.55, 0.60, 0.65])
def test_차체폭_인자가_반영된다(body_width):
    """명세 Phase 3 매트릭스 - 이 인자만 바꿔 550/600/650 실험이 돌아야 한다."""
    urdf = render(body_width=body_width)
    link = next(l for l in urdf.findall("link") if l.get("name") == "base_link")
    size = [float(v) for v in link.find("visual/geometry/box").get("size").split()]
    assert size[1] == pytest.approx(body_width)
    collision = [float(v) for v in link.find("collision/geometry/box").get("size").split()]
    assert collision[1] == pytest.approx(body_width), "콜리전이 비주얼과 어긋나면 실험이 무의미하다"


@pytest.mark.parametrize("wheel_separation", [0.40, 0.45, 0.50])
def test_바퀴간격_인자가_반영된다(wheel_separation):
    tree = UrdfTree(render(wheel_separation=wheel_separation))
    left, _ = tree.link_pose("left_wheel_link")
    right, _ = tree.link_pose("right_wheel_link")
    assert left[1] - right[1] == pytest.approx(wheel_separation, abs=1e-9)


def test_차체폭을_바꿔도_총질량은_유지된다():
    for width in (0.55, 0.65):
        total, _ = UrdfTree(render(body_width=width)).center_of_mass()
        assert total == pytest.approx(60.0, abs=1e-9)


# ------------------------------------------------------- 치수 원본과의 동기화
ARG_TO_YAML = {
    "wheel_separation": "drive.wheel_separation",
    "body_width": "body.width",
    "body_depth": "body.depth",
    "body_height": "body.height",
    "wheel_radius": "drive.wheel_radius",
    "wheelbase": "chassis.wheelbase",
    "total_mass": "chassis.total_mass",
}

PROPERTY_TO_YAML = {
    "wheel_width": "drive.wheel_width",
    "caster_radius": "caster.radius",
    "drive_load_ratio": "chassis.drive_load_ratio",
    "caster_separation": "caster.separation",
    "ground_clearance": "body.ground_clearance",
    "wheel_mass": "drive.wheel_mass",
    "caster_mass": "caster.mass",
    "lidar_mass": "sensors.lidar.mass",
    "lidar_range_max": "sensors.lidar.range_max",
    "lidar_range_min": "sensors.lidar.range_min",
    "lidar_scan_rate": "sensors.lidar.scan_rate",
    "imu_mass": "sensors.imu.mass",
    "camera_mass": "sensors.camera.mass",
    "camera_mount_height": "sensors.camera.mount_height",
    "drive_wheel_mu": "friction.drive_wheel_mu",
    "caster_mu": "friction.caster_mu",
}

SIZE_TO_YAML = {
    ("lidar_size_x", "lidar_size_y", "lidar_size_z"): "sensors.lidar.size",
    ("imu_size_x", "imu_size_y", "imu_size_z"): "sensors.imu.size",
    ("camera_size_x", "camera_size_y", "camera_size_z"): "sensors.camera.size",
}

XACRO_NS = "{http://www.ros.org/wiki/xacro}"


@pytest.fixture(scope="module")
def params_xacro() -> ET.Element:
    return ET.fromstring(PARAMS_XACRO.read_text(encoding="utf-8"))


def xacro_args(root: ET.Element) -> dict[str, str]:
    return {a.get("name"): a.get("default") for a in root.findall(f"{XACRO_NS}arg")}


def xacro_properties(root: ET.Element) -> dict[str, str]:
    return {p.get("name"): p.get("value") for p in root.findall(f"{XACRO_NS}property")}


@pytest.mark.parametrize("arg,path", sorted(ARG_TO_YAML.items()))
def test_xacro_인자_기본값이_yaml과_같다(params_xacro, dims, arg, path):
    """두 파일이 갈라지면 launch와 직접 렌더가 서로 다른 로봇을 만든다."""
    default = xacro_args(params_xacro)[arg]
    assert float(default) == pytest.approx(value(dims, path))


@pytest.mark.parametrize("prop,path", sorted(PROPERTY_TO_YAML.items()))
def test_xacro_속성이_yaml과_같다(params_xacro, dims, prop, path):
    assert float(xacro_properties(params_xacro)[prop]) == pytest.approx(value(dims, path))


@pytest.mark.parametrize("props,path", sorted(SIZE_TO_YAML.items()))
def test_센서_치수가_yaml과_같다(params_xacro, dims, props, path):
    actual = [float(xacro_properties(params_xacro)[p]) for p in props]
    assert actual == pytest.approx(value(dims, path))


def test_모든_치수가_출처를_가진다(dims):
    """명세 서문 규칙 - 근거 없는 수치를 조용히 확정하지 않는다."""
    found = 0

    def walk(node):
        nonlocal found
        if not isinstance(node, dict):
            return
        if "value" in node and "confidence" in node:
            found += 1
            assert node.get("source", "").strip(), f"출처가 비어 있다: {node}"
            assert node["confidence"] in {"spec", "spec_draft", "todo"}
            return
        for child in node.values():
            walk(child)

    walk(dims)
    assert found > 0


def test_명세_확정값이_유지된다(dims):
    """명세 §3 기준값. 바뀌면 하드웨어 사양과 시뮬이 어긋난다."""
    assert value(dims, "drive.wheel_radius") == 0.1  # 지름 200mm
    assert value(dims, "drive.wheel_width") == 0.05
    assert value(dims, "caster.radius") == 0.05  # 지름 100mm
    assert value(dims, "chassis.total_mass") == 60.0
    assert value(dims, "chassis.drive_load_ratio") == 0.6
    assert value(dims, "sensors.lidar.range_max") == 12.0
    assert value(dims, "motion.max_speed") == 1.0
    assert value(dims, "motion.nominal_speed") == 0.6
