"""Shared fixtures for renderer golden tests."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mqi.contracts import parse_contract
from mqi.ir import MissionIR, compile_ir
from mqi.policy import GuardDecision

_GOLDEN_DIR = Path(__file__).parent / "golden"

# Canonical multi-workload contract: spans device classes, priority bands, and a `shed` fallback.
# (Guard-valid for ops-admin, but these tests use a fake allow-guard — no opa needed.)
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
def mission_ir() -> MissionIR:
    return compile_ir(parse_contract(FIXTURE_CONTRACT), guard=_allow)


@pytest.fixture
def golden() -> Callable[[str, str], None]:
    """Assert `actual` byte-equals golden/<name>; MQI_GOLDEN_UPDATE=1 rewrites it."""

    def _assert(name: str, actual: str) -> None:
        path = _GOLDEN_DIR / name
        if os.environ.get("MQI_GOLDEN_UPDATE"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual)
            return
        assert path.read_text() == actual, f"{name} differs; run `make golden-update` if intended"

    return _assert
