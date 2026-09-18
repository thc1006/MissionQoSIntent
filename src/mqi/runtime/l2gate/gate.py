"""The deferred-red L2 admission gate: slack-aware admit / defer / drop over a bounded queue.

State machine (ADR-0004, SDD §6.2), evaluated at arrival (`submit`) and while waiting (`tick`):
with `remaining_slack = deadline_ms - now` and `est_min_service` from the live load signal, drop
when `remaining_slack < est_min_service * (1 - drop_relaxation)` (doomed → yield capacity), else
admit when a slot is free, else defer in the bounded queue.
"""

from __future__ import annotations

from mqi.ir import IRWorkload
from mqi.runtime.clock import Clock
from mqi.runtime.l2gate.models import Decision, GateMetrics, Outcome, Request
from mqi.runtime.l2gate.ordering import OrderingKey, fcfs
from mqi.runtime.l2gate.signals import LoadSignal


class DeferredRedGate:
    """An in-process admission gate enforcing the IR-derived L2 deferred-red policy."""

    def __init__(
        self,
        *,
        clock: Clock,
        load: LoadSignal,
        max_queue: int,
        ordering: OrderingKey = fcfs,
        metrics: GateMetrics | None = None,
    ) -> None:
        self._clock = clock
        self._load = load
        self._max_queue = max_queue
        self._ordering = ordering
        self._deferred: dict[str, Request] = {}
        self.metrics = metrics if metrics is not None else GateMetrics()

    def _redline_breached(self, request: Request, now_ms: int) -> bool:
        """True when doomed: slack below the assurance-tuned min-service threshold."""
        remaining_slack = request.deadline_ms - now_ms
        threshold = self._load.estimate_min_service_ms() * (1.0 - request.drop_relaxation)
        return remaining_slack < threshold

    def _record_drop(self, request_id: str, reason: str) -> Decision:
        self.metrics.dropped += 1
        self.metrics.drop_reasons[reason] = self.metrics.drop_reasons.get(reason, 0) + 1
        return Decision.DROP

    def submit(self, request: Request) -> Decision:
        """Arrival transition: drop the doomed, admit under capacity, else defer."""
        if request.id in self._deferred:
            return Decision.DEFER  # idempotent: already waiting — do not re-enqueue or double-count
        now = self._clock.now_ms()
        if self._redline_breached(request, now):
            return self._record_drop(request.id, request.on_drop)
        if self._load.available_slots() >= 1:
            self.metrics.admitted += 1
            return Decision.ADMIT
        if len(self._deferred) >= self._max_queue:
            return self._record_drop(request.id, "queue_full")
        self._deferred[request.id] = request.model_copy(update={"enqueued_at_ms": now})
        self.metrics.deferred += 1
        return Decision.DEFER

    def is_pending(self, request_id: str) -> bool:
        """True if a request with this id is currently deferred (waiting) in the queue.

        Lets a caller detect an id collision before submitting: `submit` treats a resubmitted
        pending id as idempotent (returns DEFER without re-enqueuing), which is right for a genuine
        retry but would silently swallow a DISTINCT request that happened to reuse an in-flight id.
        """
        return request_id in self._deferred

    def tick(self) -> Outcome | None:
        """One wait-time transition: drop a doomed deferred request, else release one, else no-op.

        Doomed-drop wins over release so freed capacity never goes to a request that cannot make
        its deadline. Breached requests are scanned in enqueue order; the release picks the best
        waiting request per the configured ordering policy. Returns None when nothing changed.
        """
        now = self._clock.now_ms()
        for request_id, request in self._deferred.items():
            if self._redline_breached(request, now):
                del self._deferred[request_id]
                self._record_drop(request_id, request.on_drop)
                return Outcome(
                    request_id=request_id, decision=Decision.DROP, reason=request.on_drop
                )
        if self._load.available_slots() >= 1 and self._deferred:
            request_id = min(self._deferred, key=lambda k: self._ordering(self._deferred[k]))
            request = self._deferred.pop(request_id)
            enqueued_at = now if request.enqueued_at_ms is None else request.enqueued_at_ms
            wait_ms = now - enqueued_at
            self.metrics.admitted += 1
            self.metrics.observe_wait(wait_ms)
            return Outcome(
                request_id=request_id, decision=Decision.ADMIT, reason="released", wait_ms=wait_ms
            )
        return None


def build_request(workload: IRWorkload, request_id: str, arrival_ms: int) -> Request:
    """Derive an admission Request from an IR workload's L2 policy.

    Same source Stage-4 renders and Stage-5 verifies: `deadline_ms` is the arrival time plus the
    L2 slack basis, `drop_relaxation` = 1 - assurance, `on_drop` is the workload fallback.
    """
    return Request(
        id=request_id,
        priority=workload.priority,
        deadline_ms=arrival_ms + workload.targets.l2.slack_basis_ms,
        on_drop=workload.fallback,
        drop_relaxation=workload.targets.l2.drop_relaxation,
    )
