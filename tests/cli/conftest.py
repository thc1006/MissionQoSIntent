"""Fixtures for the mqi CLI integration tests: a valid contract written to a temp file."""

from __future__ import annotations

from pathlib import Path

import pytest

CONTRACT = """
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


@pytest.fixture
def contract_file(tmp_path: Path) -> Path:
    path = tmp_path / "contract.yaml"
    path.write_text(CONTRACT)
    return path
