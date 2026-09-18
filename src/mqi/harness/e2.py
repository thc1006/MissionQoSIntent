"""Experiment E2: control-path value vs data-path throughput (orthogonality; SDD §10.2, R-2).

Pure metrics only — the load is driven by `experiments/e2` against a REAL vLLM on the GPU and the
deployed L2/L3 admission gate. Under a NON-overload offered load, two conditions:
  * baseline — requests go straight to vLLM (no admission policy).
  * gated    — each request is admitted by the L2/L3 gate first, then sent to vLLM.

SCOPE (deliberately narrow — the guard/gate DECISION correctness is E1/E3's job, not E2's): E2 shows
only that inserting the admission control path is ORTHOGONAL to data-path throughput. The acceptance
therefore guards against the ways a throughput ratio ≈ 1 could be a lie:
  * a load-SHEDDING gate would also keep the GPU saturated (ratio ≈ 1) — so the gate's ADMIT rate
    must be ≈ 1 (dropping/deferring lowers it, catching even ~2% shed). A rare transient completion
    failure lowers the SUCCESS rate instead, which is tolerated so an orthogonal run doesn't flap.
  * an invalid (mostly-failing) baseline inflates the ratio — so the baseline completeness is
    floored too, and the gate's per-request overhead is measured DIRECTLY (the isolated /admit
    round-trip), not as a difference of two noisy cross-run latencies.
Acceptance = throughput_ratio >= min_ratio AND admit_rate >= min_admit_rate AND both success rates
>= min_success_rate AND honest accounting (successes <= admitted). Conditions are run in alternating
rounds so run-order (GPU warm-up) does not bias the ratio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestSample:
    """One request: end-to-end latency, success, and (gated only) the admit decision + cost."""

    latency_ms: float
    ok: bool
    admitted: bool | None = None  # None baseline; True/False gated
    admit_latency_ms: float | None = None  # gated only: the ISOLATED /admit round-trip time


@dataclass(frozen=True)
class ConditionMetrics:
    """Aggregate metrics for one condition (baseline or gated)."""

    condition: str
    requests: int
    successes: int
    admitted: int | None  # None for baseline
    success_rate: float  # successes / requests — did the DATA PATH complete the offered load
    admit_rate: float | None  # gated: admitted / requests — did the GATE admit (not shed) the load
    wall_seconds: float
    throughput_rps: float
    p50_ms: float
    p99_ms: float
    admit_overhead_ms: float | None  # gated: mean isolated /admit latency (successful admits only)


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated q-th percentile (q in [0, 100]); 0.0 for an empty sample."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (q / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def summarize_condition(
    condition: str, samples: list[RequestSample], wall_seconds: float
) -> ConditionMetrics:
    """Fold raw samples into throughput + latency percentiles + completeness for one condition."""
    ok_latencies = [s.latency_ms for s in samples if s.ok]
    successes = len(ok_latencies)
    requests = len(samples)
    is_gated = any(s.admitted is not None for s in samples)
    admitted = sum(1 for s in samples if s.admitted) if is_gated else None
    admit_rate = (admitted / requests if requests > 0 else 0.0) if admitted is not None else None
    admit_costs = [s.admit_latency_ms for s in samples if s.admit_latency_ms is not None]
    admit_overhead = sum(admit_costs) / len(admit_costs) if admit_costs else None
    return ConditionMetrics(
        condition=condition,
        requests=requests,
        successes=successes,
        admitted=admitted,
        success_rate=successes / requests if requests > 0 else 0.0,
        admit_rate=admit_rate,
        wall_seconds=wall_seconds,
        throughput_rps=successes / wall_seconds if wall_seconds > 0 else 0.0,
        p50_ms=percentile(ok_latencies, 50),
        p99_ms=percentile(ok_latencies, 99),
        admit_overhead_ms=admit_overhead,
    )


@dataclass(frozen=True)
class E2Summary:
    """Orthogonality verdict: gated vs baseline throughput + completeness, plus acceptance."""

    baseline: ConditionMetrics
    gated: ConditionMetrics
    throughput_ratio: float  # gated / baseline (≈ 1 when the control path is orthogonal)
    gate_overhead_ms: float  # the DIRECT isolated /admit round-trip cost (gated only)
    min_ratio: float
    min_success_rate: float
    min_admit_rate: float
    accepted: bool


def summarize(
    baseline: ConditionMetrics,
    gated: ConditionMetrics,
    *,
    min_ratio: float = 0.95,
    min_success_rate: float = 0.97,
    min_admit_rate: float = 0.99,
) -> E2Summary:
    """Decide orthogonality acceptance, separating gate-SHEDDING from transient completion failures.

    A load-shedding gate lowers the ADMIT rate (it drops/defers) — guarded by min_admit_rate, so
    even a 1-2% shed fails. A rare transient vLLM error lowers the SUCCESS rate (admitted, failed)
    — tolerated by a slightly-slack min_success_rate so an orthogonal run does not flap to REJECTED.
    """
    ratio = gated.throughput_rps / baseline.throughput_rps if baseline.throughput_rps > 0 else 0.0
    accepted = (
        baseline.requests > 0
        and gated.requests > 0
        and baseline.success_rate >= min_success_rate  # the baseline actually served (valid)
        and gated.admit_rate is not None
        and gated.admit_rate >= min_admit_rate  # the gate ADMITTED the load — did NOT shed
        and gated.success_rate >= min_success_rate  # the admitted load actually completed
        and gated.admitted is not None
        and gated.successes <= gated.admitted  # honest: nothing completes without being admitted
        and ratio >= min_ratio
    )
    return E2Summary(
        baseline=baseline,
        gated=gated,
        throughput_ratio=ratio,
        gate_overhead_ms=gated.admit_overhead_ms if gated.admit_overhead_ms is not None else 0.0,
        min_ratio=min_ratio,
        min_success_rate=min_success_rate,
        min_admit_rate=min_admit_rate,
        accepted=accepted,
    )
