"""L5 renderer: GAIE InferencePool + EndpointPickerConfig (consume, not rebuild — ADR-0006).

InferencePool is on the stable v1 group; EndpointPickerConfig is the experimental startup-read
config (.../v1alpha1, ledger D2); the `flowControl` gate is default-off (D9) so it is enabled
explicitly. Ordering/fairness = slo-deadline / global-strict (D4/D5); defaultRequestTTL is a flat
backstop = max deadline (D7; per-request slack handled by L2).
"""

from __future__ import annotations

from typing import Any

from mqi.ir import MissionIR
from mqi.renderers.yaml_util import dump_manifests

_GAIE_POOL = "inference.networking.k8s.io/v1"
_GAIE_EPP = "inference.networking.x-k8s.io/v1alpha1"


def render_l5(ir: MissionIR) -> str:
    """Render L5 GAIE manifests (InferencePool + EndpointPickerConfig) for a mission IR."""
    mission = ir.mission
    priorities = sorted({w.priority for w in ir.workloads}, reverse=True)
    max_deadline_ms = max(w.deadline_ms for w in ir.workloads)

    inference_pool: dict[str, Any] = {
        "apiVersion": _GAIE_POOL,
        "kind": "InferencePool",
        "metadata": {"name": f"{mission}-pool"},
        "spec": {
            "selector": {"matchLabels": {"app": f"{mission}-inference"}},
            "targetPorts": [{"number": 8000}],
            "endpointPickerRef": {"name": f"{mission}-epp", "port": {"number": 9002}},
        },
    }

    epp_config: dict[str, Any] = {
        "apiVersion": _GAIE_EPP,
        "kind": "EndpointPickerConfig",
        "featureGates": ["flowControl"],
        "flowControl": {
            "defaultRequestTTL": f"{max_deadline_ms}ms",
            "priorityBands": [
                {
                    "priority": priority,
                    "orderingPolicyRef": "slo-deadline-ordering-policy",
                    "fairnessPolicyRef": "global-strict-fairness-policy",
                }
                for priority in priorities
            ],
        },
        "saturationDetector": {
            "type": "utilization-detector",
            "queueDepthThreshold": 5,
            "kvCacheUtilThreshold": 0.8,
            "headroom": 0.0,
        },
    }

    return dump_manifests([inference_pool, epp_config])
