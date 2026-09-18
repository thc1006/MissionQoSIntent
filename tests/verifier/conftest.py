"""Shared fixtures for the cross-layer verifier tests."""

from __future__ import annotations

from typing import Any

import pytest

from mqi.contracts import parse_contract
from mqi.ir import MissionIR, compile_ir
from mqi.policy import GuardDecision
from mqi.renderers import render_l2, render_l4, render_l5

# Canonical multi-workload contract (device classes + priority bands + a `shed` fallback).
FIXTURE_CONTRACT = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: ops-admin
  mission: urban-edge-2026
spec:
  workloads:
    - missionClass: emergency-routing
      priority: 100
      slo:
        deadline: 500ms
      throughputFloorRps: 50
      resourceClass: gpu-40g
      assuranceRatio: 0.999
      fallback: reject-with-reason
    - missionClass: city-monitoring
      priority: 50
      slo:
        deadline: 5s
      throughputFloorRps: 100
      resourceClass: gpu-24g
      assuranceRatio: 0.95
      fallback: degrade
    - missionClass: historical-analysis
      priority: 10
      slo:
        deadline: 60s
      resourceClass: gpu-24g
      assuranceRatio: 0.5
      fallback: shed
"""


def _allow(_contract_json: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=True, reasons=())


@pytest.fixture
def ir() -> MissionIR:
    return compile_ir(parse_contract(FIXTURE_CONTRACT), guard=_allow)


@pytest.fixture
def rendered(ir: MissionIR) -> tuple[str, str, str]:
    """The consistent (l2, l4, l5) rendered bundle for `ir`."""
    return render_l2(ir), render_l4(ir), render_l5(ir)
