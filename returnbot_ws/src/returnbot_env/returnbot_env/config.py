"""config/env_types.yaml 로더.

yaml의 모든 치수는 {value, confidence, source} 매핑이다. 이 모듈이 그 껍질을 벗겨
값만 돌려주고, 동시에 근거(provenance)를 조회할 수 있게 한다.
명세 §7 "파라미터 전부 yaml, 매직넘버 금지"를 지키는 유일한 진입점이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .ir import Material

#: 근거 확보 실패를 뜻하는 신뢰도. 이 값들은 임의 확정 금지 (명세 서문).
CONFIDENCE_TODO = "todo"
CONFIDENCE_REFERENCE = "reference"
CONFIDENCE_CONFIRMED = "confirmed"

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "env_types.yaml"

_MISSING = object()


@dataclass(frozen=True)
class Provenance:
    path: str
    value: Any
    confidence: str
    source: str

    @property
    def is_todo(self) -> bool:
        return self.confidence == CONFIDENCE_TODO


class EnvConfig:
    def __init__(self, data: dict, path: Path | None = None) -> None:
        self._data = data
        self.path = path

    @classmethod
    def load(cls, path: str | Path | None = None) -> "EnvConfig":
        resolved = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        with open(resolved, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh), resolved)

    # ------------------------------------------------------------------ 조회
    def node(self, dotted: str, default: Any = _MISSING) -> Any:
        """점 구분 경로로 원본 노드를 가져온다 ({value,confidence,source} 포함)."""
        cursor: Any = self._data
        for key in dotted.split("."):
            if not isinstance(cursor, dict) or key not in cursor:
                if default is _MISSING:
                    raise KeyError(f"env_types.yaml 에 없는 경로: {dotted}")
                return default
            cursor = cursor[key]
        return cursor

    def get(self, dotted: str, default: Any = _MISSING) -> Any:
        """치수 값만 가져온다. value 키를 가진 매핑이면 그 값을 벗겨낸다."""
        node = self.node(dotted, default)
        if isinstance(node, dict) and "value" in node:
            return node["value"]
        return node

    def provenance(self, dotted: str) -> Provenance:
        node = self.node(dotted)
        if not isinstance(node, dict) or "value" not in node:
            raise TypeError(f"{dotted} 는 근거를 가진 치수 노드가 아니다")
        return Provenance(
            path=dotted,
            value=node["value"],
            confidence=node.get("confidence", CONFIDENCE_TODO),
            source=node.get("source", ""),
        )

    def all_provenance(self) -> list[Provenance]:
        """yaml 전체를 훑어 근거를 가진 노드를 모두 모은다 (리포트 생성용)."""
        found: list[Provenance] = []

        def walk(node: Any, path: str) -> None:
            if not isinstance(node, dict):
                return
            if "value" in node and "confidence" in node:
                found.append(
                    Provenance(
                        path=path,
                        value=node["value"],
                        confidence=node.get("confidence", CONFIDENCE_TODO),
                        source=node.get("source", ""),
                    )
                )
                return
            for key, child in node.items():
                walk(child, f"{path}.{key}" if path else key)

        walk(self._data, "")
        return found

    def todo_items(self) -> list[Provenance]:
        return [p for p in self.all_provenance() if p.is_todo]

    # ---------------------------------------------------------------- 재질
    def material(self, name: str) -> Material:
        node = self.node(f"materials.{name}")
        return Material(
            name=name,
            mu=float(node["mu"]),
            mu2=float(node["mu2"]),
            rgba=tuple(float(c) for c in node["rgba"]),
        )

    def type_names(self) -> list[str]:
        return list(self.node("types").keys())
