"""IR compile tests (guard injected as a fake unless noted).

Test list (Canon TDD):
1. contract -> IR happy path
2. IR rejected when the policy guard denies (PolicyDenied carries reasons)
3. content-hash is stable across runs (determinism) and sensitive to changes
4. provenance back-links resolve to the source contract workload
5. L1-L5 target annotations present and internally consistent
6. real opa-eval guard integration (allow + deny) [see test_guard_integration.py]
"""

from typing import Any

import pytest

from mqi.contracts import parse_contract
from mqi.ir import MissionIR, compile_ir, resolve_contract_path
from mqi.policy import GuardDecision, PolicyDenied

MINIMAL = """
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
"""


TWO_WORKLOADS = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: city-ops
  mission: urban-edge-2026
spec:
  workloads:
    - missionClass: incident-verification
      priority: 80
      slo:
        deadline: 2s
      resourceClass: gpu-40g
      assuranceRatio: 0.99
      fallback: degrade-then-reject
    - missionClass: city-monitoring
      priority: 50
      slo:
        deadline: 5s
      resourceClass: gpu-24g
      assuranceRatio: 0.95
      fallback: degrade
"""


def allow_guard(_contract_json: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=True, reasons=())


def deny_guard(_contract_json: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=False, reasons=("workload criticality exceeds entitlement",))


def test_compile_happy_path() -> None:
    contract = parse_contract(MINIMAL)

    ir = compile_ir(contract, guard=allow_guard)

    assert isinstance(ir, MissionIR)
    assert ir.ir_version == "0.1.0"
    assert ir.tenant == "city-ops"
    assert ir.mission == "urban-edge-2026"

    (workload,) = ir.workloads
    assert workload.id == "wl-0-emergency-routing"
    assert workload.mission_class == "emergency-routing"
    assert workload.priority == 100
    assert workload.deadline_ms == 500
    assert workload.device_class == "gpu-40g"
    assert workload.fallback == "reject-with-reason"


def test_compile_rejects_when_guard_denies() -> None:
    contract = parse_contract(MINIMAL)

    with pytest.raises(PolicyDenied) as exc_info:
        compile_ir(contract, guard=deny_guard)

    assert exc_info.value.reasons == ("workload criticality exceeds entitlement",)


def test_content_hash_is_deterministic_and_sensitive() -> None:
    contract = parse_contract(MINIMAL)

    hash_a = compile_ir(contract, guard=allow_guard).content_hash
    hash_b = compile_ir(contract, guard=allow_guard).content_hash

    # deterministic: recompiling the same contract yields the identical sha256 hex.
    assert hash_a == hash_b
    assert len(hash_a) == 64

    # sensitive: a structurally different contract yields a different hash.
    other = parse_contract(MINIMAL.replace("priority: 100", "priority: 90"))
    assert compile_ir(other, guard=allow_guard).content_hash != hash_a


def test_provenance_backlinks_resolve() -> None:
    contract = parse_contract(TWO_WORKLOADS)
    contract_json = contract.model_dump(mode="json", by_alias=True)

    ir = compile_ir(contract, guard=allow_guard)

    assert len(ir.workloads) == 2
    for workload in ir.workloads:
        node = resolve_contract_path(contract_json, workload.provenance.contract_field)
        assert node["missionClass"] == workload.provenance.mission_semantic
        assert workload.provenance.source == "urban-edge-2026"

    # the two back-links resolve to distinct source nodes
    fields = {w.provenance.contract_field for w in ir.workloads}
    assert fields == {"spec.workloads[0]", "spec.workloads[1]"}


def test_resolve_contract_path_rejects_invalid_segment() -> None:
    with pytest.raises(KeyError):
        resolve_contract_path({"a": 1}, "not-a-valid-segment!")
