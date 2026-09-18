"""Unit tests for the AdmissionStack facade (L3 group throttle in front of the L2 gate)."""

from __future__ import annotations

from typing import Any

import pytest

from mqi.contracts import parse_contract
from mqi.ir import MissionIR, compile_ir
from mqi.policy import GuardDecision
from mqi.renderers import render_l5
from mqi.runtime import build_admission_stack
from mqi.runtime.clock import ManualClock
from mqi.runtime.l2gate import Decision, DeferredRedGate, StaticLoad
from mqi.runtime.l3 import GroupThrottle, L3Decision, SaturationGate, StaticSaturation

# Protected tenant (fallback reject-with-reason), guaranteed floor 1 rps.
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

# Best-effort tenant, fully sheddable.
_SHED_CONTRACT = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: bulk
  mission: batch
spec:
  workloads:
    - missionClass: historical-analysis
      priority: 10
      slo:
        deadline: 60s
      throughputFloorRps: 5
      resourceClass: gpu-24g
      assuranceRatio: 0.5
      fallback: shed
"""

# Two protected workloads with different deadlines (500ms urgent, 5s slack) — for ordering.
_TWO_CONTRACT = """
apiVersion: missionqos.dev/v0
kind: MissionQoSContract
metadata:
  tenant: two
  mission: demo2
spec:
  workloads:
    - missionClass: emergency-routing
      priority: 100
      slo:
        deadline: 500ms
      throughputFloorRps: 10
      resourceClass: gpu-40g
      assuranceRatio: 0.99
      fallback: reject-with-reason
    - missionClass: city-monitoring
      priority: 50
      slo:
        deadline: 5s
      throughputFloorRps: 10
      resourceClass: gpu-24g
      assuranceRatio: 0.95
      fallback: degrade
"""


def _allow(_c: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=True, reasons=())


@pytest.fixture
def ir() -> MissionIR:
    return compile_ir(parse_contract(_CONTRACT), guard=_allow)


@pytest.fixture
def shed_ir() -> MissionIR:
    return compile_ir(parse_contract(_SHED_CONTRACT), guard=_allow)


@pytest.fixture
def ir_two() -> MissionIR:
    return compile_ir(parse_contract(_TWO_CONTRACT), guard=_allow)


def test_l3_pass_then_l2_admit_then_rate_throttle(ir: MissionIR) -> None:
    clock = ManualClock()
    stack = build_admission_stack(
        ir, clock=clock, load=StaticLoad(slots=1, min_service_ms=10),
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10, burst_seconds=1.0,  # rate 1, burst 1
    )
    w = ir.workloads[0]
    first = stack.admit(w, "r1", arrival_ms=0)
    assert first.throttle is L3Decision.PASS
    assert first.admission is Decision.ADMIT
    second = stack.admit(w, "r2", arrival_ms=0)  # bucket now empty
    assert second.throttle is L3Decision.THROTTLE
    assert second.admission is None  # short-circuited: never reached the L2 gate


def test_l3_pass_but_l2_defers_when_saturated(ir: MissionIR) -> None:
    clock = ManualClock()
    stack = build_admission_stack(
        ir, clock=clock, load=StaticLoad(slots=0, min_service_ms=10),  # no L2 capacity
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10, burst_seconds=5.0,  # burst 5 so L3 passes
    )
    result = stack.admit(ir.workloads[0], "r1", arrival_ms=0)
    assert result.throttle is L3Decision.PASS
    assert result.admission is Decision.DEFER  # deferred (recoverable), not throttled, not dropped


def test_saturation_short_circuits_sheddable_group(shed_ir: MissionIR) -> None:
    clock = ManualClock()
    stack = build_admission_stack(
        shed_ir, clock=clock, load=StaticLoad(slots=1, min_service_ms=10),
        saturation=StaticSaturation(0.95), saturation_gate=SaturationGate(high=0.8, low=0.5),
        max_queue=10, burst_seconds=5.0,
    )
    result = stack.admit(shed_ir.workloads[0], "r1", arrival_ms=0)
    assert result.throttle is L3Decision.THROTTLE  # sheddable + saturated
    assert result.admission is None  # never reached the L2 gate


def test_admit_rejects_a_foreign_workload(ir: MissionIR, shed_ir: MissionIR) -> None:
    stack = build_admission_stack(
        ir, clock=ManualClock(), load=StaticLoad(slots=1, min_service_ms=10),
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10,
    )
    foreign = shed_ir.workloads[0]
    assert foreign not in set(ir.workloads)  # precondition: genuinely foreign
    with pytest.raises(KeyError, match="not in this stack"):
        stack.admit(foreign, "r1", arrival_ms=0)


def test_tick_releases_a_deferred_request(ir: MissionIR) -> None:
    clock = ManualClock()
    load = StaticLoad(slots=0, min_service_ms=1)  # no L2 capacity -> defer
    stack = build_admission_stack(
        ir, clock=clock, load=load,
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10, burst_seconds=100.0,
    )
    assert stack.admit(ir.workloads[0], "r1", arrival_ms=0).admission is Decision.DEFER
    load.slots = 1  # capacity returns; the facade must forward tick()
    out = stack.tick()
    assert out is not None
    assert out.request_id == "r1" and out.decision is Decision.ADMIT


def test_snapshot_exposes_l2_and_l3_metrics(ir: MissionIR) -> None:
    stack = build_admission_stack(
        ir, clock=ManualClock(), load=StaticLoad(slots=1, min_service_ms=1),
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10, burst_seconds=100.0,
    )
    stack.admit(ir.workloads[0], "r1", arrival_ms=0)  # L3 pass + L2 admit
    snap = stack.snapshot()
    assert set(snap) == {"l2", "l3"}
    l2 = snap["l2"]
    assert isinstance(l2, dict) and l2["admitted"] == 1
    assert isinstance(snap["l3"], dict)


def test_default_ordering_is_deadline_aware(ir_two: MissionIR) -> None:
    clock = ManualClock()
    load = StaticLoad(slots=0, min_service_ms=1)
    stack = build_admission_stack(
        ir_two, clock=clock, load=load,
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10, burst_seconds=100.0,
    )
    urgent = ir_two.workloads[0]  # 500ms deadline
    slack = ir_two.workloads[1]  # 5s deadline
    assert stack.admit(slack, "slack", arrival_ms=0).admission is Decision.DEFER
    assert stack.admit(urgent, "urgent", arrival_ms=0).admission is Decision.DEFER
    load.slots = 1
    first = stack.tick()  # default slo_deadline ordering releases earliest-deadline first, not fcfs
    assert first is not None and first.request_id == "urgent"


def test_stack_exposes_wrapped_mechanisms(ir: MissionIR) -> None:
    stack = build_admission_stack(
        ir, clock=ManualClock(), load=StaticLoad(slots=1, min_service_ms=1),
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10,
    )
    assert isinstance(stack.gate, DeferredRedGate)
    assert isinstance(stack.throttle, GroupThrottle)


def test_admit_is_single_shot_not_idempotent(ir: MissionIR) -> None:
    # Documented scope: admit does NOT dedup retries — re-calling a used id re-evaluates from
    # scratch (a retry re-charges L3). Also a tripwire against silently re-adding a decision cache.
    clock = ManualClock()
    stack = build_admission_stack(
        ir, clock=clock, load=StaticLoad(slots=5, min_service_ms=1),
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10, burst_seconds=1.0,  # group rate 1, burst 1 -> a single L3 token
    )
    w = ir.workloads[0]
    assert stack.admit(w, "r1", arrival_ms=0).admission is Decision.ADMIT  # spends the token
    # re-calling the same id re-evaluates (no cache): L3 bucket is now empty -> THROTTLE
    assert stack.admit(w, "r1", arrival_ms=0).throttle is L3Decision.THROTTLE


def test_admit_rejects_a_request_id_already_in_flight(ir_two: MissionIR) -> None:
    # Regression guard: with the idempotency cache gone, a DISTINCT request that reuses a still-
    # in-flight id would otherwise hit the L2 gate's `id in _deferred` short-circuit and be SILENTLY
    # dropped (while charging L3). admit now rejects a still-pending id loudly, before charging L3.
    clock = ManualClock()
    stack = build_admission_stack(
        ir_two, clock=clock, load=StaticLoad(slots=0, min_service_ms=1),  # no capacity -> defer
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10, burst_seconds=100.0,
    )
    a, b = ir_two.workloads[0], ir_two.workloads[1]
    assert stack.admit(a, "dup", arrival_ms=0).admission is Decision.DEFER  # "dup" now in-flight
    l3_passed_before = stack.throttle.snapshot()["passed"]  # exactly one L3 pass so far
    with pytest.raises(ValueError, match="already in-flight"):
        stack.admit(b, "dup", arrival_ms=0)  # distinct request, same id
    assert stack.gate.metrics.deferred == 1  # b was rejected, not silently queued or dropped
    # the guard runs BEFORE charging L3, so the rejected call must not have drained a token:
    assert stack.throttle.snapshot()["passed"] == l3_passed_before  # no extra L3 pass


def test_admit_allows_reuse_of_a_released_request_id(ir: MissionIR) -> None:
    # False-positive guard: once a deferred request is released via tick() it leaves the gate, so
    # reusing its id must be allowed (is_pending reads the live queue, not a persistent seen-set).
    clock = ManualClock()
    load = StaticLoad(slots=0, min_service_ms=1)  # no capacity -> defer
    stack = build_admission_stack(
        ir, clock=clock, load=load,
        saturation=StaticSaturation(0.0), saturation_gate=SaturationGate(high=0.9, low=0.5),
        max_queue=10, burst_seconds=100.0,
    )
    w = ir.workloads[0]
    assert stack.admit(w, "r1", arrival_ms=0).admission is Decision.DEFER  # "r1" in-flight
    load.slots = 1
    assert stack.tick() is not None  # "r1" released -> popped from the gate's queue
    assert stack.admit(w, "r1", arrival_ms=0).admission is Decision.ADMIT  # id free again, no raise


def test_default_ordering_matches_rendered_l5_policy(ir_two: MissionIR) -> None:
    # Same-source tripwire: render_l5 emits slo-deadline ordering for this IR, so the runtime stack
    # must default the L2 release order to the deadline-aware policy (behaviour: the test above).
    assert "slo-deadline-ordering-policy" in render_l5(ir_two)
