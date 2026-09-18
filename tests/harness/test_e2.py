"""Unit tests for the E2 metrics (pure; the load driver lives in experiments/e2)."""

from __future__ import annotations

from mqi.harness.e2 import (
    ConditionMetrics,
    RequestSample,
    percentile,
    summarize,
    summarize_condition,
)


def test_percentile_interpolates() -> None:
    assert percentile([10, 20, 30, 40], 50) == 25.0
    assert percentile([1, 2, 3, 4, 5], 100) == 5.0
    assert percentile([1, 2, 3, 4, 5], 0) == 1.0
    assert percentile([10], 99) == 10.0
    assert percentile([], 50) == 0.0


def test_summarize_condition_baseline() -> None:
    samples = [RequestSample(10, True), RequestSample(20, True), RequestSample(0, False)]
    m = summarize_condition("baseline", samples, wall_seconds=2.0)
    assert m.requests == 3 and m.successes == 2
    assert m.throughput_rps == 1.0  # 2 successes / 2s
    assert m.admitted is None  # baseline: no admit decisions
    assert m.p50_ms == 15.0  # percentile([10,20], 50)


def test_summarize_condition_gated_counts_admits() -> None:
    samples = [
        RequestSample(12, True, admitted=True),
        RequestSample(15, True, admitted=True),
        RequestSample(0, False, admitted=False),
    ]
    m = summarize_condition("gated", samples, wall_seconds=3.0)
    assert m.admitted == 2 and m.successes == 2


def _cond(condition: str, successes: int, admitted: int | None, tput: float) -> ConditionMetrics:
    return ConditionMetrics(condition, 100, successes, admitted, 10.0, tput, 12.0, 20.0)


def test_summarize_accepts_when_orthogonal() -> None:
    base = _cond("baseline", 100, None, 10.0)
    gated = _cond("gated", 100, 100, 9.5)  # ratio 0.95 >= 0.90, admitted == successes
    s = summarize(base, gated, min_ratio=0.90)
    assert s.throughput_ratio == 0.95 and s.accepted


def test_summarize_rejects_when_throughput_drops() -> None:
    base = _cond("baseline", 100, None, 10.0)
    gated = _cond("gated", 80, 80, 8.0)  # ratio 0.80 < 0.90 -> gate hurt the data path
    assert not summarize(base, gated, min_ratio=0.90).accepted


def test_summarize_rejects_on_dishonest_accounting() -> None:
    base = _cond("baseline", 100, None, 10.0)
    gated = _cond("gated", 100, 90, 9.8)  # admitted 90 != successes 100 (over/under-counted)
    assert not summarize(base, gated).accepted


def test_summarize_rejects_empty_run() -> None:
    base = _cond("baseline", 0, None, 0.0)
    gated = _cond("gated", 100, 100, 9.5)
    assert not summarize(base, gated).accepted
