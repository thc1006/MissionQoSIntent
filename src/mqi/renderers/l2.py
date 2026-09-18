"""L2 renderer: the deferred-red admission gate's declarative config (not the runtime)."""

from __future__ import annotations

from typing import Any

from mqi.ir import MissionIR
from mqi.renderers.yaml_util import dump_document


def render_l2(ir: MissionIR) -> str:
    """Render the deferred-red gate config for a mission IR (schema per SDD example §4)."""
    gates = [
        {
            "workload": workload.id,
            "slackBasisMs": workload.targets.l2.slack_basis_ms,
            "minServiceTimeSource": "metrics",
            "dropWhen": "remaining_slack_ms < est_min_service_ms",
            "onDrop": workload.fallback,
        }
        for workload in ir.workloads
    ]
    document: dict[str, Any] = {
        "apiVersion": "missionqos.dev/v0",
        "kind": "DeferredRedGateConfig",
        "metadata": {"name": ir.mission, "tenant": ir.tenant},
        "spec": {"gates": gates},
    }
    return dump_document(document)
