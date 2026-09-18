"""Fixtures for the L3 throttle tests: compiled IRs for the group-config builder."""

from __future__ import annotations

from typing import Any

import pytest

from mqi.contracts import parse_contract
from mqi.ir import MissionIR, compile_ir
from mqi.policy import GuardDecision

# Two guaranteed workloads (floors 30 + 20 rps), neither sheddable.
_CONTRACT = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: ops
  mission: demo
spec:
  workloads:
    - missionClass: emergency-routing
      priority: 100
      slo:
        deadline: 500ms
      throughputFloorRps: 30
      resourceClass: gpu-40g
      assuranceRatio: 0.99
      fallback: reject-with-reason
    - missionClass: city-monitoring
      priority: 50
      slo:
        deadline: 5s
      throughputFloorRps: 20
      resourceClass: gpu-24g
      assuranceRatio: 0.9
      fallback: degrade
"""

# One best-effort workload with no declared floor, fully sheddable.
_SHED_CONTRACT = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: besteffort
  mission: bulk
spec:
  workloads:
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
    return compile_ir(parse_contract(_CONTRACT), guard=_allow)


@pytest.fixture
def shed_ir() -> MissionIR:
    return compile_ir(parse_contract(_SHED_CONTRACT), guard=_allow)
