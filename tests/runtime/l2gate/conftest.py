"""Fixtures for the deferred-red gate tests: a Request factory with sensible defaults."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from mqi.contracts import parse_contract
from mqi.ir import MissionIR, compile_ir
from mqi.policy import GuardDecision
from mqi.runtime.l2gate import Request


@pytest.fixture
def make_request() -> Callable[..., Request]:
    """Return a factory building a `Request`; override any field via keyword."""

    def _make(
        *,
        id: str = "r1",
        priority: int = 50,
        deadline_ms: int = 1_000,
        on_drop: str = "reject-with-reason",
        drop_relaxation: float = 0.0,
    ) -> Request:
        return Request(
            id=id,
            priority=priority,
            deadline_ms=deadline_ms,
            on_drop=on_drop,
            drop_relaxation=drop_relaxation,
        )

    return _make


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
      throughputFloorRps: 50
      resourceClass: gpu-40g
      assuranceRatio: 0.9
      fallback: reject-with-reason
"""


def _allow(_contract_json: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=True, reasons=())


@pytest.fixture
def ir() -> MissionIR:
    """A compiled single-workload IR for the `build_request` provenance test."""
    return compile_ir(parse_contract(_CONTRACT), guard=_allow)
