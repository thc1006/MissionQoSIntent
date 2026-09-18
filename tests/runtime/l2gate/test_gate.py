"""Behavioural tests for the deferred-red admission gate (fake clock + fake load, no k8s)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from mqi.ir import MissionIR
from mqi.runtime.l2gate import (
    ORDERINGS,
    Decision,
    DeferredRedGate,
    ManualClock,
    Request,
    StaticLoad,
    SystemClock,
    build_request,
)


def test_admit_under_capacity(make_request: Callable[..., Request]) -> None:
    gate = DeferredRedGate(
        clock=ManualClock(), load=StaticLoad(slots=1, min_service_ms=100), max_queue=10
    )
    assert gate.submit(make_request(deadline_ms=1_000)) is Decision.ADMIT
    assert (gate.metrics.admitted, gate.metrics.deferred, gate.metrics.dropped) == (1, 0, 0)


def test_defer_when_saturated_within_ttl(make_request: Callable[..., Request]) -> None:
    gate = DeferredRedGate(
        clock=ManualClock(), load=StaticLoad(slots=0, min_service_ms=100), max_queue=10
    )
    # slack = 1000 >= est_min_service 100 -> attainable, but no capacity -> defer.
    assert gate.submit(make_request(deadline_ms=1_000)) is Decision.DEFER
    assert (gate.metrics.admitted, gate.metrics.deferred, gate.metrics.dropped) == (0, 1, 0)


def test_drop_redline_at_submit(make_request: Callable[..., Request]) -> None:
    gate = DeferredRedGate(
        clock=ManualClock(), load=StaticLoad(slots=0, min_service_ms=600), max_queue=10
    )
    # slack = 500 < est_min_service 600 -> doomed: deferred-red drop at arrival, reason = onDrop.
    assert gate.submit(make_request(deadline_ms=500, on_drop="reject-with-reason")) is Decision.DROP
    assert gate.metrics.dropped == 1
    assert gate.metrics.drop_reasons == {"reject-with-reason": 1}


def test_drop_on_slack_breach_during_wait(make_request: Callable[..., Request]) -> None:
    clock = ManualClock()
    load = StaticLoad(slots=0, min_service_ms=100)
    gate = DeferredRedGate(clock=clock, load=load, max_queue=10)
    assert gate.submit(make_request(deadline_ms=500)) is Decision.DEFER  # slack 500 >= 100
    clock.advance(450)  # slack now 50 < est_min_service 100 -> doomed while waiting
    outcome = gate.tick()
    assert outcome is not None
    assert outcome.decision is Decision.DROP
    assert outcome.request_id == "r1"
    assert gate.metrics.dropped == 1


def test_priority_release_order(make_request: Callable[..., Request]) -> None:
    load = StaticLoad(slots=0, min_service_ms=10)
    gate = DeferredRedGate(
        clock=ManualClock(), load=load, max_queue=10, ordering=ORDERINGS["priority"]
    )
    for rid, prio in [("lo", 10), ("mid", 50), ("hi", 100)]:
        decision = gate.submit(make_request(id=rid, priority=prio, deadline_ms=100_000))
        assert decision is Decision.DEFER
    load.slots = 1  # capacity returns; one release per tick, highest priority first
    released: list[str] = []
    while (outcome := gate.tick()) is not None:
        released.append(outcome.request_id)
    assert released == ["hi", "mid", "lo"]
    assert gate.metrics.admitted == 3


def test_wait_ms_recorded(make_request: Callable[..., Request]) -> None:
    clock = ManualClock()
    load = StaticLoad(slots=0, min_service_ms=10)
    gate = DeferredRedGate(clock=clock, load=load, max_queue=10)
    assert gate.submit(make_request(deadline_ms=100_000)) is Decision.DEFER
    clock.advance(300)
    load.slots = 1
    outcome = gate.tick()
    assert outcome is not None
    assert outcome.decision is Decision.ADMIT
    assert outcome.wait_ms == 300
    assert gate.metrics.wait_ms_total == 300


@pytest.mark.parametrize("policy", ["edf", "slo_deadline"])
def test_deadline_release_order(make_request: Callable[..., Request], policy: str) -> None:
    load = StaticLoad(slots=0, min_service_ms=10)
    gate = DeferredRedGate(
        clock=ManualClock(), load=load, max_queue=10, ordering=ORDERINGS[policy]
    )
    # priorities are inverted vs deadlines: a deadline policy must ignore priority.
    for rid, deadline, prio in [("far", 30_000, 100), ("near", 10_000, 1), ("mid", 20_000, 50)]:
        decision = gate.submit(make_request(id=rid, deadline_ms=deadline, priority=prio))
        assert decision is Decision.DEFER
    load.slots = 1
    released: list[str] = []
    while (outcome := gate.tick()) is not None:
        released.append(outcome.request_id)
    assert released == ["near", "mid", "far"]


def test_queue_bound_enforced(make_request: Callable[..., Request]) -> None:
    gate = DeferredRedGate(
        clock=ManualClock(), load=StaticLoad(slots=0, min_service_ms=10), max_queue=2
    )
    assert gate.submit(make_request(id="a", deadline_ms=100_000)) is Decision.DEFER
    assert gate.submit(make_request(id="b", deadline_ms=100_000)) is Decision.DEFER
    assert gate.submit(make_request(id="c", deadline_ms=100_000)) is Decision.DROP  # queue full
    assert gate.metrics.deferred == 2
    assert gate.metrics.drop_reasons == {"queue_full": 1}


def test_idempotent_resubmit(make_request: Callable[..., Request]) -> None:
    gate = DeferredRedGate(
        clock=ManualClock(), load=StaticLoad(slots=0, min_service_ms=10), max_queue=10
    )
    assert gate.submit(make_request(id="x", deadline_ms=100_000)) is Decision.DEFER
    assert gate.submit(make_request(id="x", deadline_ms=100_000)) is Decision.DEFER  # re-submit
    assert gate.metrics.deferred == 1  # counted exactly once


def test_is_pending_reports_whether_an_id_is_waiting(
    make_request: Callable[..., Request],
) -> None:
    gate = DeferredRedGate(
        clock=ManualClock(), load=StaticLoad(slots=0, min_service_ms=10), max_queue=10
    )
    assert not gate.is_pending("x")  # nothing deferred yet
    assert gate.submit(make_request(id="x", deadline_ms=100_000)) is Decision.DEFER
    assert gate.is_pending("x")  # now waiting in the queue
    assert not gate.is_pending("y")  # a distinct id is not pending


def test_is_pending_clears_after_release(make_request: Callable[..., Request]) -> None:
    load = StaticLoad(slots=0, min_service_ms=10)  # no capacity -> defer
    gate = DeferredRedGate(clock=ManualClock(), load=load, max_queue=10)
    assert gate.submit(make_request(id="x", deadline_ms=100_000)) is Decision.DEFER
    assert gate.is_pending("x")  # waiting
    load.slots = 1  # capacity returns
    assert gate.tick() is not None  # releases "x" -> popped from the queue
    assert not gate.is_pending("x")  # id is free again; a caller may reuse it


def test_tick_noop_is_idempotent(make_request: Callable[..., Request]) -> None:
    gate = DeferredRedGate(
        clock=ManualClock(), load=StaticLoad(slots=0, min_service_ms=10), max_queue=10
    )
    assert gate.tick() is None  # empty gate
    assert gate.submit(make_request(id="y", deadline_ms=100_000)) is Decision.DEFER
    before = (gate.metrics.admitted, gate.metrics.deferred, gate.metrics.dropped)
    assert gate.tick() is None  # no capacity, no breach -> no transition
    assert gate.tick() is None
    assert (gate.metrics.admitted, gate.metrics.deferred, gate.metrics.dropped) == before


def test_snapshot(make_request: Callable[..., Request]) -> None:
    gate = DeferredRedGate(
        clock=ManualClock(), load=StaticLoad(slots=1, min_service_ms=10), max_queue=10
    )
    assert gate.submit(make_request(id="a", deadline_ms=100_000)) is Decision.ADMIT
    assert gate.metrics.snapshot() == {
        "admitted": 1,
        "deferred": 0,
        "dropped": 0,
        "wait_ms_total": 0,
        "wait_count": 0,
        "drop_reasons": {},
        "wait_histogram_le": {
            "10": 0, "50": 0, "100": 0, "250": 0,
            "500": 0, "1000": 0, "2500": 0, "5000": 0, "+Inf": 0,
        },
    }


def test_wait_histogram(make_request: Callable[..., Request]) -> None:
    clock = ManualClock()
    load = StaticLoad(slots=0, min_service_ms=1)
    gate = DeferredRedGate(clock=clock, load=load, max_queue=10)

    def release_after(rid: str, wait: int) -> None:
        assert gate.submit(make_request(id=rid, deadline_ms=1_000_000)) is Decision.DEFER
        clock.advance(wait)
        load.slots = 1
        out = gate.tick()
        assert out is not None and out.request_id == rid and out.wait_ms == wait
        load.slots = 0

    release_after("a", 5)  # bucket le 10
    release_after("b", 80)  # bucket le 100
    release_after("c", 300)  # bucket le 500
    release_after("d", 6_000)  # over the largest bucket -> +Inf overflow

    snap = gate.metrics.snapshot()
    assert snap["wait_count"] == 4
    assert snap["wait_ms_total"] == 6_385
    hist = snap["wait_histogram_le"]
    assert isinstance(hist, dict)
    # cumulative le buckets: a<=10, a+b<=100, a+b<=250, a+b+c<=500..5000, d overflows to +Inf
    assert hist["10"] == 1 and hist["100"] == 2 and hist["250"] == 2
    assert hist["500"] == 3 and hist["5000"] == 3 and hist["+Inf"] == 4


def test_build_request_from_workload(ir: MissionIR) -> None:
    workload = ir.workloads[0]
    req = build_request(workload, request_id="req-1", arrival_ms=1_000)
    assert req.id == "req-1"
    assert req.priority == workload.priority
    assert req.deadline_ms == 1_000 + workload.targets.l2.slack_basis_ms
    assert req.on_drop == workload.fallback
    assert req.drop_relaxation == workload.targets.l2.drop_relaxation


def test_relaxation_delays_drop(make_request: Callable[..., Request]) -> None:
    clock = ManualClock()
    load = StaticLoad(slots=0, min_service_ms=100)
    strict = DeferredRedGate(clock=clock, load=load, max_queue=10)
    relaxed = DeferredRedGate(clock=clock, load=load, max_queue=10)
    s_dec = strict.submit(make_request(id="s", deadline_ms=150, drop_relaxation=0.0))
    r_dec = relaxed.submit(make_request(id="r", deadline_ms=150, drop_relaxation=0.8))
    assert s_dec is Decision.DEFER
    assert r_dec is Decision.DEFER
    clock.advance(60)  # slack now 90: strict threshold 100 -> drop; relaxed threshold 20 -> keep
    strict_out = strict.tick()
    assert strict_out is not None and strict_out.decision is Decision.DROP
    assert relaxed.tick() is None


def test_manual_clock_set_and_advance() -> None:
    clock = ManualClock()
    clock.set(500)
    assert clock.now_ms() == 500
    clock.advance(10)
    assert clock.now_ms() == 510


def test_system_clock_returns_monotonic_ms() -> None:
    clock = SystemClock()
    first = clock.now_ms()
    assert isinstance(first, int)
    assert clock.now_ms() >= first
