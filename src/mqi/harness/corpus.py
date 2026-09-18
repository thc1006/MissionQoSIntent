"""Seeded corpus of QoS contracts for experiment E1 (consistency + policy-guard).

Deterministic given a seed: `generate(seed)` yields the same labeled cases every run, so E1 is
reproducible. Each `ContractCase` carries the contract YAML plus its EXPECTED verdict — a valid
contract must compile + guard-allow + verify-consistent; an adversarial contract must be REJECTED
(by the parser or the OPA guard) with a known reason fragment. The adversarial cases are pinned one
per guard rule (R1-R4, R3a/b/c, unknown-tenant) so E1 proves the guard catches each violation with
no false-allow; the valid cases are seeded-random within the entitlements in `policy/data.json`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# Mirrors policy/data.json (the guard's entitlements) — kept in sync via test_corpus round-trips.
# city-ops is non-admin, <= incident-verification (rank 3), 500 rps; system min service = 50ms.
_DEVICE_MIN_DEADLINE_MS = {"gpu-40g": 100, "gpu-24g": 500}
_MAX_INFLIGHT = 1024  # Little's law bound enforced by the contract parser (N = rps*deadline/1000)
_FALLBACKS = ("reject-with-reason", "degrade", "shed")


@dataclass(frozen=True)
class ContractCase:
    """One labeled contract: its YAML plus the verdict E1 expects."""

    id: str
    category: str  # "valid" | "R1" | "R2" | "R3a" | "R3b" | "R3c" | "R4" | "unknown-tenant"
    contract_yaml: str
    expect_reject: bool  # False => must compile + guard-allow + verify-consistent
    reason_substring: str  # a fragment UNIQUE to the expected rule's message ("" when valid)
    expected_stage: str  # "allow" for valid; "guard" for every adversarial case (all guard rules)


def _workload(
    *,
    mission: str,
    priority: int,
    deadline_ms: int,
    floor_rps: int,
    device: str,
    assurance: float,
    fallback: str,
    admin_access: bool = False,
) -> str:
    admin = "\n      adminAccess: true" if admin_access else ""
    return (
        f"    - missionClass: {mission}\n"
        f"      priority: {priority}\n"
        f"      slo:\n"
        f"        deadline: {deadline_ms}ms\n"
        f"      throughputFloorRps: {floor_rps}\n"
        f"      resourceClass: {device}\n"
        f"      assuranceRatio: {assurance}\n"
        f"      fallback: {fallback}{admin}"
    )


def _contract(tenant: str, mission_name: str, workloads: list[str]) -> str:
    body = "\n".join(workloads)
    return (
        "apiVersion: missionqos.dev/v0\n"
        "kind: MissionQoSContract\n"
        "metadata:\n"
        f"  tenant: {tenant}\n"
        f"  mission: {mission_name}\n"
        "spec:\n"
        "  workloads:\n"
        f"{body}\n"
    )


def _safe_floor(rng: random.Random, deadline_ms: int, ceiling_rps: int) -> int:
    """A floor rps that respects both the entitlement ceiling and Little's law for this deadline."""
    littles_cap = max(1, (_MAX_INFLIGHT * 1000) // deadline_ms)
    return rng.randint(1, max(1, min(ceiling_rps, littles_cap)))


def _valid_case(rng: random.Random, index: int) -> ContractCase:
    # city-ops: non-admin, <= incident-verification (rank 3), 500 rps entitlement.
    device = rng.choice(("gpu-40g", "gpu-24g"))
    min_dl = _DEVICE_MIN_DEADLINE_MS[device]
    deadline = rng.randint(min_dl, min_dl + 4500)
    floor = _safe_floor(rng, deadline, ceiling_rps=500)
    mission = rng.choice(("historical-analysis", "city-monitoring", "incident-verification"))
    workload = _workload(
        mission=mission,
        priority=rng.choice((10, 50, 100)),
        deadline_ms=deadline,
        floor_rps=floor,
        device=device,
        assurance=rng.choice((0.5, 0.9, 0.95, 0.99)),
        fallback=rng.choice(_FALLBACKS),
    )
    yaml = _contract("city-ops", f"valid-{index}", [workload])
    return ContractCase(
        f"valid-{index}", "valid", yaml, expect_reject=False, reason_substring="",
        expected_stage="allow",
    )


def _r1_over_throughput(rng: random.Random) -> ContractCase:
    # two workloads whose floors sum above city-ops' 500 rps entitlement (each Little's-law-safe).
    w = [
        _workload(
            mission="city-monitoring", priority=50, deadline_ms=1000, floor_rps=400,
            device="gpu-24g", assurance=0.9, fallback="degrade",
        ),
        _workload(
            mission="historical-analysis", priority=10, deadline_ms=1000, floor_rps=400,
            device="gpu-24g", assurance=0.5, fallback="shed",
        ),
    ]
    return ContractCase(
        "R1", "R1", _contract("city-ops", "over-throughput", w),
        expect_reject=True, reason_substring="guaranteed throughput", expected_stage="guard",
    )


def _r2_over_criticality(rng: random.Random) -> ContractCase:
    # city-ops (max incident-verification, rank 3) requesting emergency-routing (rank 4).
    w = _workload(
        mission="emergency-routing", priority=100, deadline_ms=200, floor_rps=50,
        device="gpu-40g", assurance=0.99, fallback="reject-with-reason",
    )
    return ContractCase(
        "R2", "R2", _contract("city-ops", "over-criticality", [w]),
        expect_reject=True, reason_substring="criticality", expected_stage="guard",
    )


def _r3a_unknown_device(rng: random.Random) -> ContractCase:
    w = _workload(
        mission="city-monitoring", priority=50, deadline_ms=1000, floor_rps=50,
        device="gpu-8g", assurance=0.9, fallback="degrade",
    )
    return ContractCase(
        "R3a", "R3a", _contract("city-ops", "unknown-device", [w]),
        expect_reject=True, reason_substring="not a known device class", expected_stage="guard",
    )


def _r3b_below_min_deadline(rng: random.Random) -> ContractCase:
    # deadline below the system minimum service time (50ms).
    w = _workload(
        mission="city-monitoring", priority=50, deadline_ms=10, floor_rps=50,
        device="gpu-40g", assurance=0.9, fallback="degrade",
    )
    return ContractCase(
        "R3b", "R3b", _contract("city-ops", "below-min-deadline", [w]),
        expect_reject=True,
        reason_substring="below the system minimum service time",
        expected_stage="guard",
    )


def _r3c_class_cannot_meet(rng: random.Random) -> ContractCase:
    # gpu-24g needs >=500ms; ask for 300ms (>= system min 50, so R3b is clear — isolates R3c).
    w = _workload(
        mission="city-monitoring", priority=50, deadline_ms=300, floor_rps=50,
        device="gpu-24g", assurance=0.9, fallback="degrade",
    )
    return ContractCase(
        "R3c", "R3c", _contract("city-ops", "class-cannot-meet", [w]),
        expect_reject=True, reason_substring="below device", expected_stage="guard",
    )


def _r4_admin_access(rng: random.Random) -> ContractCase:
    # non-admin city-ops requesting adminAccess.
    w = _workload(
        mission="city-monitoring", priority=50, deadline_ms=1000, floor_rps=50,
        device="gpu-24g", assurance=0.9, fallback="degrade", admin_access=True,
    )
    return ContractCase(
        "R4", "R4", _contract("city-ops", "admin-access", [w]),
        expect_reject=True, reason_substring="adminAccess", expected_stage="guard",
    )


def _unknown_tenant(rng: random.Random) -> ContractCase:
    w = _workload(
        mission="city-monitoring", priority=50, deadline_ms=1000, floor_rps=50,
        device="gpu-24g", assurance=0.9, fallback="degrade",
    )
    return ContractCase(
        "unknown-tenant", "unknown-tenant", _contract("ghost-tenant", "unknown", [w]),
        expect_reject=True, reason_substring="unknown tenant", expected_stage="guard",
    )


_ADVERSARIAL = (
    _r1_over_throughput,
    _r2_over_criticality,
    _r3a_unknown_device,
    _r3b_below_min_deadline,
    _r3c_class_cannot_meet,
    _r4_admin_access,
    _unknown_tenant,
)


def generate(seed: int, *, n_valid: int = 20) -> list[ContractCase]:
    """Deterministically build the E1 corpus: `n_valid` valid contracts + one per guard rule."""
    rng = random.Random(seed)
    cases = [_valid_case(rng, i) for i in range(n_valid)]
    cases.extend(make(rng) for make in _ADVERSARIAL)
    return cases
