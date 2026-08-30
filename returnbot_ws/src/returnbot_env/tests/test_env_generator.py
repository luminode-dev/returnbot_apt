"""Phase 0 완료 검증.

Gazebo 없이 확인할 수 있는 것만 다룬다. 실제 물리 거동(문턱 통과, 마찰)은
Phase 2에서 Gazebo로 검증한다.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from returnbot_env.backends import sdf as sdf_backend
from returnbot_env.backends import svg as svg_backend
from returnbot_env.backends import usd as usd_backend
from returnbot_env.builders import build_scene
from returnbot_env.cli import main as cli_main
from returnbot_env.config import EnvConfig
from returnbot_env.ir import Box
from returnbot_env.params import APARTMENT_TYPES, build_params

CORRIDOR_TYPES = ("A", "B")


@pytest.fixture(scope="module")
def cfg() -> EnvConfig:
    return EnvConfig.load()


def scene_for(cfg: EnvConfig, apt_type: str, **overrides):
    return build_scene(cfg, build_params(cfg, apt_type, **overrides))


# ------------------------------------------------------------------ 기본 생성
@pytest.mark.parametrize("apt_type", APARTMENT_TYPES)
def test_모든_유형이_생성된다(cfg, apt_type):
    scene = scene_for(cfg, apt_type)
    assert len(scene) > 0
    assert scene.metadata["type"] == apt_type
    names = [e.name for e in scene]
    assert len(names) == len(set(names)), "요소 이름이 중복되면 SDF 모델 이름이 충돌한다"


@pytest.mark.parametrize("apt_type", APARTMENT_TYPES)
def test_필수_구성요소가_존재한다(cfg, apt_type):
    scene = scene_for(cfg, apt_type)
    for tag in ("floor", "wall", "door", "threshold"):
        assert scene.by_tag(tag), f"유형 {apt_type} 에 {tag} 요소가 없다"


def test_편복도는_개방측_난간을_가진다(cfg):
    assert scene_for(cfg, "A").by_tag("parapet")


def test_중복도는_난간이_없고_양쪽에_문이_있다(cfg):
    scene = scene_for(cfg, "B")
    assert not scene.by_tag("parapet")
    door_y = [e.pose.y for e in scene.by_tag("door") if "fire_door" not in e.tags]
    assert any(y > 0 for y in door_y) and any(y < 0 for y in door_y)


def test_홀형은_승강기문을_가진다(cfg):
    scene = scene_for(cfg, "C")
    doors = scene.by_tag("elevator_door")
    assert len(doors) == scene.metadata["params"]["elevator_count"]


# --------------------------------------------------- 핵심: 복도 유효폭 정합성
@pytest.mark.parametrize("apt_type", CORRIDOR_TYPES)
@pytest.mark.parametrize("width", [0.9, 1.2, 1.5, 1.8])
def test_복도_유효폭이_인자와_일치한다(cfg, apt_type, width):
    """생성된 지오메트리에서 실측한 벽 안쪽면 간격이 지정 폭과 같아야 한다.

    이 값이 틀리면 Phase 3 차체폭 매트릭스 실험 전체가 무의미해진다.
    """
    scene = scene_for(cfg, apt_type, corridor_width=width, include_clutter=False)
    clear = measure_clear_width(scene)
    assert clear == pytest.approx(width, abs=1e-6)


def measure_clear_width(scene) -> float:
    """복도 중간 구간에서 좌우 벽 안쪽면 사이 거리를 실측한다."""
    length = scene.metadata["params"]["corridor_length"]
    x_probe = length * 0.5
    pos_inner, neg_inner = math.inf, -math.inf
    for element in scene:
        if not (element.has_tag("wall") or element.has_tag("parapet")):
            continue
        pts = element.footprint()
        if min(p[0] for p in pts) > x_probe or max(p[0] for p in pts) < x_probe:
            continue  # 이 x 위치를 지나지 않는 벽(끝벽 등)은 제외
        ys = [p[1] for p in pts]
        if min(ys) >= 0:
            pos_inner = min(pos_inner, min(ys))
        if max(ys) <= 0:
            neg_inner = max(neg_inner, max(ys))
    assert math.isfinite(pos_inner) and math.isfinite(neg_inner), "양측 벽을 찾지 못했다"
    return pos_inner - neg_inner


@pytest.mark.parametrize("apt_type", CORRIDOR_TYPES)
def test_적치물은_복도_밖으로_나가지_않는다(cfg, apt_type):
    """회전한 긴 물건(자전거)이 벽을 뚫으면 Gazebo에서 물리가 폭주한다."""
    scene = scene_for(cfg, apt_type, obstacle_density=1.0, seed=7)
    half = scene.metadata["params"]["corridor_width"] / 2.0
    assert scene.by_tag("clutter"), "밀도 1.0 이면 반드시 배치되어야 한다"
    for element in scene.by_tag("clutter"):
        ys = [p[1] for p in element.footprint()]
        assert min(ys) >= -half - 1e-9
        assert max(ys) <= half + 1e-9


# ------------------------------------------------------------------ 재현성
@pytest.mark.parametrize("apt_type", CORRIDOR_TYPES)
def test_같은_시드는_같은_배치를_만든다(cfg, apt_type):
    """Phase 3 매트릭스 실험을 재현하려면 시드 결정성이 필수다."""
    a = scene_for(cfg, apt_type, obstacle_density=0.6, seed=42)
    b = scene_for(cfg, apt_type, obstacle_density=0.6, seed=42)
    c = scene_for(cfg, apt_type, obstacle_density=0.6, seed=43)
    fp = lambda s: [(e.name, e.pose.as_tuple()) for e in s.by_tag("clutter")]
    assert fp(a) == fp(b)
    assert fp(a) != fp(c)


def test_적치물_비활성화(cfg):
    assert not scene_for(cfg, "A", include_clutter=False).by_tag("clutter")


# ------------------------------------------------------------------ 문턱·경사로
@pytest.mark.parametrize("height", [0.005, 0.015, 0.020])
def test_문턱_높이가_인자를_따른다(cfg, height):
    scene = scene_for(cfg, "A", threshold_height=height)
    for element in scene.by_tag("threshold"):
        assert isinstance(element.geometry, Box)
        assert element.geometry.size[2] == pytest.approx(height)


def test_경사로_구배가_인자를_따른다(cfg):
    grade = 0.08
    scene = scene_for(cfg, "A", ramp_grade=grade)
    ramp = scene.by_tag("ramp")
    assert len(ramp) == 1
    # pitch = -atan(grade)
    assert ramp[0].pose.pitch == pytest.approx(-math.atan(grade), abs=1e-9)
    d = scene.metadata["derived"]
    run = d["ramp_x1"] - d["ramp_x0"]
    assert run == pytest.approx(d["ramp_rise"] / grade, rel=1e-9)


def test_경사로_이후_바닥이_단차만큼_올라간다(cfg):
    scene = scene_for(cfg, "A")
    d = scene.metadata["derived"]
    upper = next(e for e in scene if e.name == "floor_upper")
    top_z = upper.pose.z + upper.geometry.size[2] / 2.0
    assert top_z == pytest.approx(d["ramp_rise"], abs=1e-9)


def test_경사로_이후_세대의_문턱이_올라간_바닥_위에_있다(cfg):
    scene = scene_for(cfg, "A")
    d = scene.metadata["derived"]
    rise = d["ramp_rise"]
    after = [e for e in scene.by_tag("threshold") if e.pose.x > d["ramp_x1"]]
    assert after, "경사로 뒤에도 세대가 있어야 이 검증이 의미가 있다"
    for element in after:
        bottom = element.pose.z - element.geometry.size[2] / 2.0
        assert bottom == pytest.approx(rise, abs=1e-9)


# ------------------------------------------------------------------ 방화문
def test_방화문_상태가_전환된다(cfg):
    closed = scene_for(cfg, "C", fire_door_closed=True)
    opened = scene_for(cfg, "C", fire_door_closed=False)
    assert any(e.name.endswith("_panel") for e in closed.by_tag("fire_door"))
    assert any(e.name.endswith("_leaf_open") for e in opened.by_tag("fire_door"))


# ------------------------------------------------------------------ SDF 백엔드
@pytest.mark.parametrize("apt_type", APARTMENT_TYPES)
@pytest.mark.parametrize("flavor", ["fortress", "harmonic"])
def test_sdf가_유효한_xml이다(cfg, apt_type, flavor):
    text = sdf_backend.to_sdf(scene_for(cfg, apt_type), flavor)
    root = ET.fromstring(text)
    assert root.tag == "sdf"
    world = root.find("world")
    assert world is not None
    assert len(world.findall("model")) == len(scene_for(cfg, apt_type))
    assert world.find("light") is not None


def test_sdf_플러그인이_flavor에_따라_바뀐다(cfg):
    scene = scene_for(cfg, "A")
    fortress = ET.fromstring(sdf_backend.to_sdf(scene, "fortress"))
    harmonic = ET.fromstring(sdf_backend.to_sdf(scene, "harmonic"))
    f_names = {p.get("name") for p in fortress.find("world").findall("plugin")}
    h_names = {p.get("name") for p in harmonic.find("world").findall("plugin")}
    assert all(n.startswith("ignition::") for n in f_names)
    assert all(n.startswith("gz::") for n in h_names)


def test_sdf_flavor_오타는_거부된다(cfg):
    with pytest.raises(ValueError):
        sdf_backend.to_sdf(scene_for(cfg, "A"), "garden")


def test_sdf가_마찰계수를_싣는다(cfg):
    root = ET.fromstring(sdf_backend.to_sdf(scene_for(cfg, "A")))
    mus = root.findall(".//collision/surface/friction/ode/mu")
    assert mus and all(float(m.text) > 0 for m in mus)


def test_sdf_주석에_생성인자가_남는다(cfg):
    """월드 파일만 보고도 어떤 인자로 만들었는지 알 수 있어야 재현이 된다."""
    text = sdf_backend.to_sdf(scene_for(cfg, "A", corridor_width=1.5))
    assert '"corridor_width": 1.5' in text
    ET.fromstring(text)  # 주석 안의 '- -' 치환이 깨지지 않았는지


# ------------------------------------------------------------------ SVG 백엔드
@pytest.mark.parametrize("apt_type", APARTMENT_TYPES)
def test_svg가_유효한_xml이다(cfg, apt_type):
    root = ET.fromstring(svg_backend.to_svg(scene_for(cfg, apt_type)))
    assert root.tag.endswith("svg")
    assert root.findall(".//{http://www.w3.org/2000/svg}polygon")


# ------------------------------------------------------------------ USD 백엔드
def test_usd는_아직_구현되지_않았음을_명시한다(cfg):
    """Phase 4 이월. 조용히 빈 파일을 만드는 것보다 명시적 실패가 낫다."""
    assert usd_backend.IMPLEMENTED is False
    with pytest.raises(NotImplementedError):
        usd_backend.to_usd(scene_for(cfg, "A"), "out.usd")


# ------------------------------------------------------------------ 인자 검증
def test_잘못된_유형은_거부된다(cfg):
    with pytest.raises(ValueError):
        build_params(cfg, "Z")


@pytest.mark.parametrize(
    "override", [{"corridor_width": -1.0}, {"unit_count": 0}, {"obstacle_density": 1.5}]
)
def test_말이_안되는_인자는_거부된다(cfg, override):
    with pytest.raises(ValueError):
        build_params(cfg, "A", **override)


def test_세대가_복도보다_길면_거부된다(cfg):
    with pytest.raises(ValueError, match="복도 길이"):
        scene_for(cfg, "A", unit_count=50)


# ------------------------------------------------------------------ 근거 관리
def test_모든_치수가_출처를_가진다(cfg):
    """명세 서문 규칙 - 근거 없는 수치를 조용히 확정하지 않는다."""
    entries = cfg.all_provenance()
    assert entries
    for item in entries:
        assert item.source.strip(), f"{item.path} 에 출처가 비어 있다"
        assert item.confidence in {"confirmed", "reference", "todo"}


def test_TODO_치수가_추적되고_있다(cfg):
    todos = {p.path for p in cfg.todo_items()}
    # 실측이 필요한 핵심 항목들. 근거가 확보되면 이 목록에서 빠진다.
    assert "common.threshold.height" in todos
    assert "common.door.width" in todos


def test_법정_확정치가_유지된다(cfg):
    """피난·방화규칙 제15조의2 제1항. 이 값이 바뀌면 기준 월드의 의미가 사라진다."""
    assert cfg.provenance("types.A.corridor_width").value == 1.2
    assert cfg.provenance("types.B.corridor_width").value == 1.8
    assert cfg.provenance("common.elevator.door_width").value == 0.8


# ------------------------------------------------------------------ CLI
def test_cli가_3유형을_생성한다(tmp_path):
    """명세 §6 Phase 0 완료 기준 - 인자만 바꿔 3유형 월드가 생성된다."""
    rc = cli_main(["--all", "--out", str(tmp_path), "--svg-dir", str(tmp_path)])
    assert rc == 0
    for apt_type in APARTMENT_TYPES:
        sdf_file = tmp_path / f"apt_type_{apt_type.lower()}.sdf"
        svg_file = tmp_path / f"apt_type_{apt_type.lower()}.svg"
        assert sdf_file.exists() and svg_file.exists()
        ET.parse(sdf_file)
        ET.parse(svg_file)


def test_cli_폭_오버라이드가_파일에_반영된다(tmp_path):
    cli_main(["--type", "A", "--corridor-width", "0.9", "--out", str(tmp_path), "--name", "narrow"])
    text = (tmp_path / "narrow.sdf").read_text(encoding="utf-8")
    assert '"corridor_width": 0.9' in text


def test_cli_list_todo(capsys):
    assert cli_main(["--list-todo"]) == 0
    assert "근거 미확보" in capsys.readouterr().out


def test_cli는_유형_없이는_실패한다():
    with pytest.raises(SystemExit):
        cli_main([])
