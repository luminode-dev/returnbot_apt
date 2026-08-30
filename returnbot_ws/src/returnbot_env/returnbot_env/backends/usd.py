"""IR → USD 백엔드 (Phase 4에서 구현).

명세 §6은 "Gazebo world(sdf)와 USD를 동일 소스에서 생성"을 요구한다. 그 '동일 소스'는
ir.Scene이고, SDF 백엔드가 이미 그 계약을 검증했다. 여기서는 계약만 고정해 두고
실구현은 Isaac Sim을 실제로 붙이는 Phase 4로 미룬다.

지금 구현하지 않는 이유: Isaac Sim이 없는 상태에서 만든 USD는 로드 검증이 불가능해
"돌아가는지 모르는 코드"가 된다. IR이 확정되어 있으므로 나중에 이 파일만 채우면 된다.

구현 시 IR 계약 (backends/sdf.py 와 동일하게 지켜야 하는 것):
    - 좌표계: ir 모듈 docstring의 X=길이축 / Y=폭축 / Z=상방, RPY = Rz·Ry·Rx
    - 단위: m. USD는 metersPerUnit=1.0 으로 스테이지를 열 것
    - Element.geometry: Box → UsdGeom.Cube(scale로 크기 부여) 또는 Mesh,
      Cylinder → UsdGeom.Cylinder
    - Element.collision=True 인 것에만 UsdPhysics.CollisionAPI 적용
    - Element.static=True 이면 RigidBodyAPI를 붙이지 않는다 (정적 콜라이더)
    - Element.material.mu/mu2 → UsdPhysics.MaterialAPI 의 dynamicFriction/staticFriction
    - Element.material.rgba → UsdPreviewSurface diffuseColor + opacity
    - Scene.metadata 는 스테이지 customLayerData 에 그대로 실을 것 (재현성)

의존성: `pip install usd-core` (Windows/Linux 모두 휠 제공). Isaac Sim 내장 USD와도 호환.
"""

from __future__ import annotations

from ..ir import Scene

#: Phase 4 착수 시 이 상수를 True 로 바꾸고 to_usd 를 채운다.
IMPLEMENTED = False


def to_usd(scene: Scene, path: str) -> str:
    """Scene을 USD 스테이지로 저장하고 경로를 돌려준다.

    Raises:
        NotImplementedError: 항상. 위 docstring의 구현 계약을 참고할 것.
    """
    raise NotImplementedError(
        "USD 백엔드는 Phase 4에서 구현한다. "
        "IR 계약은 returnbot_env/backends/usd.py 의 docstring 참조. "
        f"(요청된 씬: {scene.name}, 경로: {path})"
    )
