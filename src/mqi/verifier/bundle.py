"""Parse the rendered L2/L4/L5 YAML artifacts into a structured bundle for checking."""

from __future__ import annotations

from typing import Any

import yaml
from yaml.events import AliasEvent
from yaml.nodes import Node


class _NoAliasSafeLoader(yaml.SafeLoader):
    """A SafeLoader that rejects YAML aliases, bounding alias expansion (a 'billion laughs' DoS)."""

    def compose_node(self, parent: Node | None, index: int) -> Node | None:
        if self.check_event(AliasEvent):  # type: ignore[no-untyped-call]  # types-PyYAML gap
            raise yaml.YAMLError("YAML aliases are not permitted in a rendered bundle")
        return super().compose_node(parent, index)


class RenderedBundle:
    """The rendered artifacts, parsed from their YAML bytes (so injected edits are caught)."""

    def __init__(
        self, l2: dict[str, Any], l4: list[dict[str, Any]], l5: list[dict[str, Any]]
    ) -> None:
        self.l2 = l2
        self.l4 = l4
        self.l5 = l5

    @classmethod
    def parse(cls, l2: str, l4: str, l5: str) -> RenderedBundle:
        """Parse the three artifacts; raise ValueError on malformed YAML or wrong top-level shape.

        A verifier fed hand-edited/persisted artifacts must reject garbage cleanly rather than
        crash deep in an invariant check, so the structure (L2 mapping, L4/L5 sequences of
        mappings) is validated here.
        """
        try:
            l2_doc = yaml.load(l2, Loader=_NoAliasSafeLoader)
            l4_docs = [d for d in yaml.load_all(l4, Loader=_NoAliasSafeLoader) if d is not None]
            l5_docs = [d for d in yaml.load_all(l5, Loader=_NoAliasSafeLoader) if d is not None]
        except yaml.YAMLError as exc:
            raise ValueError(f"malformed YAML in rendered bundle: {exc}") from exc
        if not isinstance(l2_doc, dict):
            raise ValueError(f"L2 artifact must be a mapping, got {type(l2_doc).__name__}")
        if not all(isinstance(d, dict) for d in l4_docs):
            raise ValueError("L4 artifact must be a sequence of mappings")
        if not all(isinstance(d, dict) for d in l5_docs):
            raise ValueError("L5 artifact must be a sequence of mappings")
        return cls(l2_doc, l4_docs, l5_docs)

    def l4_of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [d for d in self.l4 if d.get("kind") == kind]

    def l5_of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [d for d in self.l5 if d.get("kind") == kind]
