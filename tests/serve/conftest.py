"""Fixtures for the admission-service tests: a service factory over a small single-workload IR."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from mqi.contracts import parse_contract
from mqi.ir import MissionIR, compile_ir
from mqi.policy import GuardDecision
from mqi.runtime.clock import ManualClock
from mqi.serve import AdmissionService

# Single protected workload, 500ms deadline, floor 1 rps (so L3 capacity == burst_seconds tokens).
WORKLOAD_ID = "wl-0-emergency-routing"
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
      throughputFloorRps: 1
      resourceClass: gpu-40g
      assuranceRatio: 0.99
      fallback: reject-with-reason
"""


def _allow(_contract_json: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=True, reasons=())


@pytest.fixture
def ir() -> MissionIR:
    return compile_ir(parse_contract(_CONTRACT), guard=_allow)


@pytest.fixture
def make_service(ir: MissionIR) -> Callable[..., AdmissionService]:
    """Factory: an AdmissionService over the fixture IR with a ManualClock pinned at t=0."""

    def _make(*, burst_seconds: float = 100.0, max_queue: int = 10) -> AdmissionService:
        return AdmissionService(
            ir, clock=ManualClock(), max_queue=max_queue, burst_seconds=burst_seconds
        )

    return _make
