"""Contract parser tests.

Test list (Canon TDD) — one passing test per item:
1. valid minimal contract parses
2. missing required field                -> code="missing"
3. invalid SLO: zero/negative deadline   -> code="greater_than"
   invalid SLO: p99Latency > deadline    -> code="slo_incoherent"
4. unknown missionClass/criticality      -> code="enum"
5. deadline vs throughput (Little's law) -> code="deadline_throughput_conflict"
6. extra unknown field (strict)          -> code="extra_forbidden"
7. round-trip parse->dump->parse identity
Additional robustness:
8. malformed / non-mapping YAML          -> code="invalid_yaml"
9. invalid duration scalar (str/bool)    -> code="invalid_duration"
"""

import pytest

from mqi.contracts import (
    ContractError,
    MissionClass,
    MissionQoSContract,
    dump_contract,
    parse_contract,
)

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


def test_valid_minimal_contract_parses() -> None:
    contract = parse_contract(MINIMAL)

    assert isinstance(contract, MissionQoSContract)
    assert contract.metadata.tenant == "city-ops"
    assert contract.metadata.mission == "urban-edge-2026"

    (workload,) = contract.spec.workloads
    assert workload.mission_class is MissionClass.EMERGENCY_ROUTING
    assert workload.priority == 100
    assert workload.slo.deadline_ms == 500
    assert workload.slo.p99_latency_ms is None
    assert workload.throughput_floor_rps is None
    assert workload.resource_class == "gpu-40g"
    assert workload.assurance_ratio == 0.999


MISSING_TENANT = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
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


def test_missing_required_field_raises_contract_error() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(MISSING_TENANT)

    error = exc_info.value
    assert error.code == "missing"
    assert error.path == "metadata.tenant"


ZERO_DEADLINE = """
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
        deadline: 0ms
      resourceClass: gpu-40g
      assuranceRatio: 0.999
      fallback: reject-with-reason
"""

P99_EXCEEDS_DEADLINE = """
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
        p99Latency: 600ms
      resourceClass: gpu-40g
      assuranceRatio: 0.999
      fallback: reject-with-reason
"""


def test_zero_deadline_is_invalid_slo() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(ZERO_DEADLINE)

    error = exc_info.value
    assert error.code == "greater_than"
    assert error.path == "spec.workloads[0].slo.deadline"


def test_p99_exceeding_deadline_is_incoherent() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(P99_EXCEEDS_DEADLINE)

    error = exc_info.value
    assert error.code == "slo_incoherent"
    assert error.path == "spec.workloads[0].slo"


UNKNOWN_MISSION_CLASS = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: city-ops
  mission: urban-edge-2026
spec:
  workloads:
    - missionClass: satellite-imaging
      priority: 100
      slo:
        deadline: 500ms
      resourceClass: gpu-40g
      assuranceRatio: 0.999
      fallback: reject-with-reason
"""


def test_unknown_mission_class_is_rejected() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(UNKNOWN_MISSION_CLASS)

    error = exc_info.value
    assert error.code == "enum"
    assert error.path == "spec.workloads[0].missionClass"


# N = throughputFloorRps * deadlineMs / 1000 = 5000 * 1000 / 1000 = 5000 > MAX_INFLIGHT (1024)
DEADLINE_THROUGHPUT_CONFLICT = """
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
        deadline: 1s
      throughputFloorRps: 5000
      resourceClass: gpu-40g
      assuranceRatio: 0.999
      fallback: reject-with-reason
"""

# N = 100 * 1000 / 1000 = 100 <= 1024 -> feasible
FEASIBLE_THROUGHPUT = """
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
        deadline: 1s
      throughputFloorRps: 100
      resourceClass: gpu-24g
      assuranceRatio: 0.95
      fallback: degrade
"""


def test_deadline_throughput_conflict_is_rejected() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(DEADLINE_THROUGHPUT_CONFLICT)

    error = exc_info.value
    assert error.code == "deadline_throughput_conflict"
    assert error.path == "spec.workloads[0]"


def test_feasible_throughput_floor_parses() -> None:
    contract = parse_contract(FEASIBLE_THROUGHPUT)
    assert contract.spec.workloads[0].throughput_floor_rps == 100.0


EXTRA_FIELD = """
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
      bogusField: nope
"""


def test_extra_unknown_field_is_rejected() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(EXTRA_FIELD)

    error = exc_info.value
    assert error.code == "extra_forbidden"
    assert error.path == "spec.workloads[0].bogusField"


# Exercises every optional field (p99Latency, throughputFloorRps) plus a minimal workload.
FULL_CONTRACT = """
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
        p99Latency: 1500ms
      throughputFloorRps: 100
      resourceClass: gpu-40g
      assuranceRatio: 0.99
      fallback: degrade-then-reject
    - missionClass: historical-analysis
      priority: 10
      slo:
        deadline: 60s
      resourceClass: gpu-24g
      assuranceRatio: 0.5
      fallback: shed
"""


def test_round_trip_parse_dump_parse_identity() -> None:
    original = parse_contract(FULL_CONTRACT)

    reparsed = parse_contract(dump_contract(original))

    assert reparsed == original


# --- Additional robustness (see docstring) ---

MALFORMED_YAML = "apiVersion: missionqos.dev/v0\nmetadata: {tenant: [unclosed"
NON_MAPPING = "- just\n- a list\n"


def _with_deadline(value: str) -> str:
    return f"""
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
        deadline: {value}
      resourceClass: gpu-40g
      assuranceRatio: 0.999
      fallback: reject-with-reason
"""


def test_malformed_yaml_raises_contract_error() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(MALFORMED_YAML)
    assert exc_info.value.code == "invalid_yaml"


def test_non_mapping_document_raises_contract_error() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(NON_MAPPING)
    assert exc_info.value.code == "invalid_yaml"


def test_invalid_duration_string_is_rejected() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(_with_deadline("later"))
    error = exc_info.value
    assert error.code == "invalid_duration"
    assert error.path == "spec.workloads[0].slo.deadline"


def test_boolean_duration_is_rejected() -> None:
    with pytest.raises(ContractError) as exc_info:
        parse_contract(_with_deadline("true"))
    assert exc_info.value.code == "invalid_duration"
