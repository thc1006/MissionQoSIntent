"""Behavioural tests for the L3 group-throttling mechanism (fake clock, no k8s)."""

from __future__ import annotations

import pytest

from mqi.ir import MissionIR
from mqi.runtime.clock import ManualClock
from mqi.runtime.l2gate import Decision as L2Decision
from mqi.runtime.l2gate import DeferredRedGate, Request, StaticLoad
from mqi.runtime.l3 import (
    GroupConfig,
    GroupThrottle,
    L3Decision,
    SaturationGate,
    StaticSaturation,
    TokenBucket,
    group_config_from_ir,
)


def _quiet_throttle(groups: dict[str, GroupConfig], clock: ManualClock) -> GroupThrottle:
    """A throttle whose saturation gate never opens (signal pinned at 0)."""
    return GroupThrottle(
        groups=groups, clock=clock, saturation=StaticSaturation(0.0),
        gate=SaturationGate(high=0.9, low=0.5),
    )


def test_token_bucket_refill_is_exact() -> None:
    bucket = TokenBucket(rate_per_sec=10.0, burst=100.0, tokens=0.0)
    # first observation sets the baseline (no refill); then +5.0 tokens accrue over 500ms
    assert bucket.try_consume(now_ms=1_000, n=1.0) is False
    assert bucket.level == 0.0
    assert bucket.try_consume(now_ms=1_500, n=5.0) is True
    assert bucket.level == 0.0


def test_token_bucket_allows_burst_up_to_size() -> None:
    bucket = TokenBucket(rate_per_sec=1.0, burst=5.0)  # starts full at 5
    for _ in range(5):
        assert bucket.try_consume(now_ms=0) is True
    assert bucket.try_consume(now_ms=0) is False  # burst exhausted, no time elapsed
    assert bucket.try_consume(now_ms=1_000) is True  # +1 token after 1s


def test_saturation_gate_hysteresis() -> None:
    gate = SaturationGate(high=0.8, low=0.5)
    assert gate.is_open is False
    assert gate.update(0.7) is False  # below high -> stays closed
    assert gate.update(0.85) is True  # >= high -> opens
    assert gate.update(0.6) is True  # inside the band -> holds open
    assert gate.update(0.5) is False  # <= low -> closes
    assert gate.update(0.79) is False  # inside the band but was closed -> holds closed
    assert gate.update(0.8) is True  # >= high -> reopens


def test_saturation_gate_requires_high_above_low() -> None:
    with pytest.raises(ValueError, match="high > low"):
        SaturationGate(high=0.5, low=0.5)


def test_group_throttle_passes_within_rate_then_throttles() -> None:
    clock = ManualClock()
    throttle = _quiet_throttle({"t": GroupConfig(name="t", rate_per_sec=5.0, burst=3.0)}, clock)
    for _ in range(3):  # burst of 3
        assert throttle.admit("t") is L3Decision.PASS
    assert throttle.admit("t") is L3Decision.THROTTLE  # bucket empty -> rate throttle
    assert throttle.metrics.throttled_by_reason == {"rate": 1}
    assert throttle.metrics.passed == 3


def test_group_isolation_burst_cannot_starve_another_group() -> None:
    clock = ManualClock()
    groups = {
        "a": GroupConfig(name="a", rate_per_sec=1.0, burst=2.0),
        "b": GroupConfig(name="b", rate_per_sec=1.0, burst=2.0),
    }
    throttle = _quiet_throttle(groups, clock)
    # group A drains its whole bucket (and then some)
    assert throttle.admit("a") is L3Decision.PASS
    assert throttle.admit("a") is L3Decision.PASS
    assert throttle.admit("a") is L3Decision.THROTTLE  # A exhausted
    # B's guaranteed rate + burst are untouched by A's demand — separate buckets
    assert throttle.admit("b") is L3Decision.PASS
    assert throttle.admit("b") is L3Decision.PASS
    assert throttle.admit("b") is L3Decision.THROTTLE
    assert throttle.metrics.throttled_by_group == {"a": 1, "b": 1}


def test_saturation_sheds_sheddable_but_protects_guaranteed() -> None:
    clock = ManualClock()
    groups = {
        "shed": GroupConfig(name="shed", rate_per_sec=100.0, burst=100.0, sheddable=True),
        "keep": GroupConfig(name="keep", rate_per_sec=100.0, burst=100.0, sheddable=False),
    }
    sat = StaticSaturation(0.0)
    throttle = GroupThrottle(
        groups=groups, clock=clock, saturation=sat, gate=SaturationGate(high=0.8, low=0.5)
    )
    assert throttle.admit("shed") is L3Decision.PASS  # not saturated
    assert throttle.admit("keep") is L3Decision.PASS
    sat.value = 0.9  # saturate -> gate opens
    assert throttle.admit("shed") is L3Decision.THROTTLE  # sheddable shed under saturation
    assert throttle.admit("keep") is L3Decision.PASS  # protected keeps its guaranteed rate
    assert throttle.metrics.throttled_by_reason == {"saturation": 1}
    sat.value = 0.4  # recover below low -> gate closes (hysteresis)
    assert throttle.admit("shed") is L3Decision.PASS


def test_throttle_is_transient_not_a_drop() -> None:
    clock = ManualClock()
    throttle = _quiet_throttle({"t": GroupConfig(name="t", rate_per_sec=2.0, burst=1.0)}, clock)
    assert throttle.admit("t") is L3Decision.PASS  # burst of 1 consumed
    assert throttle.admit("t") is L3Decision.THROTTLE  # empty -> rate throttle
    clock.advance(1_000)  # +2 tokens/s over 1s refills the bucket
    assert throttle.admit("t") is L3Decision.PASS  # same request now passes: throttle was transient
    assert "DROP" not in L3Decision.__members__  # L3 has no terminal drop state


def test_l2_l3_interaction_throttled_is_deferred_not_dropped() -> None:
    clock = ManualClock()
    l3 = _quiet_throttle({"t": GroupConfig(name="t", rate_per_sec=1.0, burst=1.0)}, clock)
    assert l3.admit("t") is L3Decision.PASS
    assert l3.admit("t") is L3Decision.THROTTLE  # L3 throttles the excess request
    # a throttled request is not dropped: handed to the L2 gate it DEFERS (transient), unlike a drop
    l2 = DeferredRedGate(
        clock=clock, load=StaticLoad(slots=0, min_service_ms=10), max_queue=10
    )
    decision = l2.submit(Request(id="r", priority=50, deadline_ms=1_000_000, on_drop="reject"))
    assert decision is L2Decision.DEFER  # deferred (recoverable), not the L2 gate's terminal DROP


def test_snapshot_reports_events_and_token_levels() -> None:
    clock = ManualClock()
    groups = {
        "a": GroupConfig(name="a", rate_per_sec=10.0, burst=2.0),
        "b": GroupConfig(name="b", rate_per_sec=10.0, burst=2.0, sheddable=True),
    }
    sat = StaticSaturation(0.0)
    throttle = GroupThrottle(
        groups=groups, clock=clock, saturation=sat, gate=SaturationGate(high=0.8, low=0.5)
    )
    assert throttle.admit("a") is L3Decision.PASS
    assert throttle.admit("a") is L3Decision.PASS
    assert throttle.admit("a") is L3Decision.THROTTLE  # a empty -> rate
    sat.value = 0.9
    assert throttle.admit("b") is L3Decision.THROTTLE  # b sheddable + saturated -> saturation
    snap = throttle.snapshot()
    assert snap["passed"] == 2
    assert snap["throttled"] == 2
    assert snap["throttled_by_reason"] == {"rate": 1, "saturation": 1}
    assert snap["throttled_by_group"] == {"a": 1, "b": 1}
    assert snap["saturation_open"] is True
    levels = snap["token_levels"]
    assert isinstance(levels, dict)
    assert levels["a"] == 0.0 and levels["b"] == 2.0  # a drained; b never touched its bucket


def test_group_config_from_ir_protected(ir: MissionIR) -> None:
    cfg = group_config_from_ir(ir)
    assert cfg.name == "ops"
    assert cfg.rate_per_sec == 50.0  # sum of throughput floors 30 + 20
    assert cfg.burst == 50.0  # a 1s window at 50 rps
    assert cfg.sheddable is False  # not every workload is 'shed'


def test_group_config_from_ir_sheddable_and_min_burst(shed_ir: MissionIR) -> None:
    cfg = group_config_from_ir(shed_ir)
    assert cfg.name == "besteffort"
    assert cfg.rate_per_sec == 0.0  # no declared floor
    assert cfg.burst == 1.0  # max(1.0, 0 * burst_seconds) floor
    assert cfg.sheddable is True  # every workload is 'shed'


def test_token_bucket_rejects_negative_parameters() -> None:
    with pytest.raises(ValueError, match="rate_per_sec must be >= 0"):
        TokenBucket(rate_per_sec=-1.0, burst=10.0)
    with pytest.raises(ValueError, match="burst must be >= 0"):
        TokenBucket(rate_per_sec=1.0, burst=-10.0)


def test_token_bucket_rejects_negative_consume() -> None:
    bucket = TokenBucket(rate_per_sec=1.0, burst=5.0)
    with pytest.raises(ValueError, match="negative number of tokens"):
        bucket.try_consume(now_ms=0, n=-1.0)


def test_admit_unknown_group_raises() -> None:
    groups = {"known": GroupConfig(name="known", rate_per_sec=1.0, burst=1.0)}
    throttle = _quiet_throttle(groups, ManualClock())
    with pytest.raises(KeyError, match="unknown group"):
        throttle.admit("nope")


def test_group_config_from_ir_rejects_empty_workloads() -> None:
    with pytest.raises(ValueError, match="no workloads"):
        group_config_from_ir(MissionIR(tenant="t", mission="m", workloads=()))
