"""Deterministic YAML serialization for rendered manifests (stable bytes for golden tests)."""

from __future__ import annotations

from typing import Any

import yaml


class _NoAliasDumper(yaml.SafeDumper):
    """A SafeDumper that never emits YAML anchors/aliases (inlines a repeated object instead).

    Keeps rendered artifacts alias-free by construction, so the verifier's no-alias parser (which
    rejects aliases to bound 'billion laughs' expansion) accepts a freshly-rendered bundle even if a
    renderer ever reuses the same dict/list object in two positions.
    """

    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump_document(document: dict[str, Any]) -> str:
    """Serialize a single manifest/config as deterministic YAML (insertion order preserved)."""
    return yaml.dump(document, Dumper=_NoAliasDumper, sort_keys=False, default_flow_style=False)


def dump_manifests(manifests: list[dict[str, Any]]) -> str:
    """Serialize manifests as a deterministic multi-document YAML string (`---`-separated)."""
    return yaml.dump_all(
        manifests,
        Dumper=_NoAliasDumper,
        sort_keys=False,
        default_flow_style=False,
        explicit_start=True,
    )
