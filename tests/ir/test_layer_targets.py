"""L1-L5 layer-target annotations: present on every IR node and internally consistent."""

from typing import Any

import pytest
from pydantic import ValidationError

from mqi.contracts import parse_contract
from mqi.ir import compile_ir
from mqi.ir.models import (
    IRWorkload,
    L1Target,
    L2Target,
    L3Target,
    L4Target,
    L5Target,
    LayerTargets,
    Provenance,
)
from mqi.policy import GuardDecision

_SHED = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: city-ops
  mission: urban-edge-2026
spec:
  workloads:
    - missionClass: emergency-routing
      priority: 100
      slo:
        deadline: 500ms
      resourceClass: gpu-40g
      assuranceRatio: 0.999
      fallback: reject-with-reason
    - missionClass: historical-analysis
      priority: 10
      slo:
        deadline: 60s
      resourceClass: gpu-24g
      assuranceRatio: 0.5
      fallback: shed
"""


def _allow(_cj: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=True, reasons=())


def test_layer_targets_present_and_consistent() -> None:
    ir = compile_ir(parse_contract(_SHED), guard=_allow)

    for w in ir.workloads:
        t = w.targets
        # deadline aligned L2 slack == deadline == L5 ttl
        assert t.l2.slack_basis_ms == w.deadline_ms == t.l5.request_ttl_ms
        # priority monotone across L4 class value == priority == L5 band
        assert t.l4.priority_class_value == w.priority == t.l5.priority_band
        # device class aligned across L1/L4/L5
        assert t.l1.device_class == w.device_class == t.l4.device_class == t.l5.backend_class
        # fallback shed <=> L5 sheddable and L2 drop
        sheddable = w.fallback == "shed"
        assert t.l5.sheddable == sheddable
        assert (t.l2.on_drop == "drop") == sheddable

    # L1 carries the vLLM MSP metrics it consumes
    assert "vllm:num_requests_waiting" in ir.workloads[0].targets.l1.metrics


def _aligned() -> dict[str, Any]:
    return {
        "l1": L1Target(device_class="gpu-40g", metrics=()),
        "l2": L2Target(slack_basis_ms=500, on_drop="reject", drop_relaxation=0.0),
        "l3": L3Target(group="city-ops", token_bucket_share=0.0),
        "l4": L4Target(priority_class_value=100, device_class="gpu-40g", reserved_ratio=0.0),
        "l5": L5Target(
            priority_band=100, request_ttl_ms=500, sheddable=False, backend_class="gpu-40g"
        ),
    }


def _workload(targets: LayerTargets) -> IRWorkload:
    return IRWorkload(
        id="wl-x",
        mission_class="emergency-routing",
        priority=100,
        deadline_ms=500,
        p99_latency_ms=None,
        assurance_ratio=0.999,
        device_class="gpu-40g",
        throughput_floor_rps=None,
        fallback="reject-with-reason",
        targets=targets,
        provenance=Provenance(
            contract_field="spec.workloads[0]",
            mission_semantic="emergency-routing",
            source="m",
        ),
    )


def test_aligned_workload_is_accepted() -> None:
    _workload(LayerTargets(**_aligned()))


@pytest.mark.parametrize(
    "override",
    [
        {
            "l5": L5Target(
                priority_band=100, request_ttl_ms=999, sheddable=False, backend_class="gpu-40g"
            )
        },
        {"l4": L4Target(priority_class_value=7, device_class="gpu-40g", reserved_ratio=0.0)},
        {"l1": L1Target(device_class="gpu-24g", metrics=())},
        {"l2": L2Target(slack_basis_ms=500, on_drop="drop", drop_relaxation=0.0)},
    ],
)
def test_inconsistent_workload_is_rejected(override: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _workload(LayerTargets(**(_aligned() | override)))
