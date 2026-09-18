"""Integration: compile_ir gated by the REAL opa-eval policy guard (skipped if opa is absent)."""

import shutil
from pathlib import Path

import pytest

from mqi.contracts import parse_contract
from mqi.ir import MissionIR, compile_ir
from mqi.policy import PolicyDenied
from mqi.policy.guard import GuardUnavailable, evaluate

pytestmark = pytest.mark.skipif(shutil.which("opa") is None, reason="opa binary not installed")

VALID = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: city-ops
  mission: urban-edge-2026
spec:
  workloads:
    - missionClass: city-monitoring
      priority: 50
      slo:
        deadline: 5s
      throughputFloorRps: 100
      resourceClass: gpu-24g
      assuranceRatio: 0.95
      fallback: degrade
"""

DENIED = VALID.replace("tenant: city-ops", "tenant: ghost-tenant")


def test_real_guard_allows_valid_contract() -> None:
    ir = compile_ir(parse_contract(VALID))  # default guard = real opa eval

    assert isinstance(ir, MissionIR)
    assert ir.tenant == "city-ops"


def test_real_guard_denies_unknown_tenant() -> None:
    with pytest.raises(PolicyDenied) as exc_info:
        compile_ir(parse_contract(DENIED))

    assert any("unknown tenant" in reason for reason in exc_info.value.reasons)


def test_evaluate_raises_on_bad_policy_dir() -> None:
    with pytest.raises(GuardUnavailable):
        evaluate(
            {"metadata": {"tenant": "city-ops"}, "spec": {"workloads": []}},
            policy_dir=Path("/nonexistent-policy-dir"),
        )
