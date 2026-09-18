"""Pluggable release-ordering policies for the deferred queue (lowest key released first).

The names mirror GAIE Flow-Control's vocabulary so E3 can drive the gate with the same policy
string it configures on the baseline, isolating the deferred-red early-drop as the sole difference.
"""

from __future__ import annotations

from collections.abc import Callable

from mqi.runtime.l2gate.models import Request

OrderingKey = Callable[[Request], tuple[int, ...]]


def fcfs(request: Request) -> tuple[int, ...]:
    """First-come-first-served: by enqueue time."""
    return (request.enqueued_at_ms or 0,)


def priority(request: Request) -> tuple[int, ...]:
    """Highest priority first, ties broken by enqueue time."""
    return (-request.priority, request.enqueued_at_ms or 0)


def edf(request: Request) -> tuple[int, ...]:
    """Earliest deadline first, ties broken by enqueue time."""
    return (request.deadline_ms, request.enqueued_at_ms or 0)


def slo_deadline(request: Request) -> tuple[int, ...]:
    """GAIE-parity name for deadline ordering (SLO deadline measured from receipt)."""
    return (request.deadline_ms, request.enqueued_at_ms or 0)


ORDERINGS: dict[str, OrderingKey] = {
    "fcfs": fcfs,
    "priority": priority,
    "edf": edf,
    "slo_deadline": slo_deadline,
}
