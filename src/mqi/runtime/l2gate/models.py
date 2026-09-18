"""Value types for the L2 deferred-red gate: decisions, requests, outcomes, metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(frozen=True)


class Decision(StrEnum):
    """The three admission outcomes for a request (ADR-0004 deferred-red)."""

    ADMIT = "admit"
    DEFER = "defer"
    DROP = "drop"


class Request(BaseModel):
    """An in-flight admission request, carrying its IR-derived L2 policy.

    Fields are same-sourced from `IRWorkload` via `build_request`: `deadline_ms` is the
    absolute wall-clock deadline (arrival + `slack_basis_ms`), `drop_relaxation` = 1 - assurance,
    `on_drop` is the fallback string used as the drop reason.
    """

    model_config = _FROZEN

    id: str
    priority: int
    deadline_ms: int
    on_drop: str
    drop_relaxation: float = 0.0
    enqueued_at_ms: int | None = None


class Outcome(BaseModel):
    """A machine-readable record of one gate transition (emitted by `tick`)."""

    model_config = _FROZEN

    request_id: str
    decision: Decision
    reason: str
    wait_ms: int = 0


DEFAULT_WAIT_BUCKETS_MS: tuple[int, ...] = (10, 50, 100, 250, 500, 1_000, 2_500, 5_000)


@dataclass
class GateMetrics:
    """Mutable gate counters: admit/defer/drop tallies, drop reasons, wait-time histogram."""

    admitted: int = 0
    deferred: int = 0
    dropped: int = 0
    wait_ms_total: int = 0
    wait_count: int = 0
    drop_reasons: dict[str, int] = field(default_factory=dict)
    wait_buckets_ms: tuple[int, ...] = DEFAULT_WAIT_BUCKETS_MS
    wait_histogram: dict[str, int] = field(default_factory=dict)

    def observe_wait(self, wait_ms: int) -> None:
        """Record one release wait time into the sum, the count, and its histogram bucket."""
        self.wait_ms_total += wait_ms
        self.wait_count += 1
        label = "+Inf"
        for bound in self.wait_buckets_ms:
            if wait_ms <= bound:
                label = str(bound)
                break
        self.wait_histogram[label] = self.wait_histogram.get(label, 0) + 1

    def snapshot(self) -> dict[str, object]:
        """A deterministic point-in-time view for logging / E3 export.

        `wait_histogram_le` is a cumulative `le` (≤ upper-bound) histogram over `wait_buckets_ms`;
        its `+Inf` bucket equals `wait_count`.
        """
        cumulative: dict[str, int] = {}
        running = 0
        for bound in self.wait_buckets_ms:
            running += self.wait_histogram.get(str(bound), 0)
            cumulative[str(bound)] = running
        cumulative["+Inf"] = running + self.wait_histogram.get("+Inf", 0)
        return {
            "admitted": self.admitted,
            "deferred": self.deferred,
            "dropped": self.dropped,
            "wait_ms_total": self.wait_ms_total,
            "wait_count": self.wait_count,
            "drop_reasons": dict(sorted(self.drop_reasons.items())),
            "wait_histogram_le": cumulative,
        }
