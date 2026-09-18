"""Contract adminAccess field (DRA privileged device access; gates policy-guard R4)."""

from mqi.contracts import dump_contract, parse_contract

_BASE = """
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
{admin}
"""


def _contract(admin_line: str = "") -> str:
    return _BASE.format(admin=admin_line)


def test_admin_access_defaults_false() -> None:
    contract = parse_contract(_contract())
    assert contract.spec.workloads[0].admin_access is False


def test_admin_access_true_parses_and_round_trips() -> None:
    contract = parse_contract(_contract("      adminAccess: true"))
    assert contract.spec.workloads[0].admin_access is True
    assert parse_contract(dump_contract(contract)) == contract
