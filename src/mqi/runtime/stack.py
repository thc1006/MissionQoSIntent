"""A clean interface composing the L3 group throttle in front of the L2 admission gate.

Both mechanisms are built from the same compiled IR (`build_admission_stack`). A request is first
group-throttled (L3); only if it passes does it reach the per-request deferred-red gate (L2). The
facade forwards the gate's wait-time `tick()` and exposes both mechanisms' metrics, while each layer
stays independently unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from mqi.ir import IRWorkload, MissionIR
from mqi.runtime.clock import Clock
from mqi.runtime.l2gate import (
    ORDERINGS,
    Decision,
    DeferredRedGate,
    LoadSignal,
    OrderingKey,
    Outcome,
    build_request,
)
from mqi.runtime.l3 import (
    GroupThrottle,
    L3Decision,
    SaturationGate,
    SaturationSignal,
    group_config_from_ir,
)


@dataclass(frozen=True)
class AdmitResult:
    """The layered outcome: the L3 throttle decision and, if it passed, the L2 gate decision."""

    throttle: L3Decision
    admission: Decision | None  # None when L3 throttled — the request never reached the L2 gate


class AdmissionStack:
    """Composes L3 group throttling in front of the L2 deferred-red gate for one tenant group."""

    def __init__(
        self,
        *,
        gate: DeferredRedGate,
        throttle: GroupThrottle,
        group: str,
        workloads_by_id: dict[str, IRWorkload],
    ) -> None:
        self._gate = gate
        self._throttle = throttle
        self._group = group
        self._workloads_by_id = workloads_by_id

    @property
    def gate(self) -> DeferredRedGate:
        """The wrapped L2 deferred-red gate (metrics / advanced use)."""
        return self._gate

    @property
    def throttle(self) -> GroupThrottle:
        """The wrapped L3 group throttle (metrics / advanced use)."""
        return self._throttle

    def admit(self, workload: IRWorkload, request_id: str, arrival_ms: int) -> AdmitResult:
        """Make one admission decision: L3 group throttle, then (if it passes) the L2 gate.

        SINGLE-SHOT: call once per request with a unique `request_id`. It does NOT dedup retries or
        reconcile with later `tick()` transitions — re-calling a used id re-evaluates from scratch
        and may re-charge L3. Exactly-once admission (retry dedup / TTL) is a serving-layer concern
        kept outside this facade. `workload` must be one from this stack's IR (matched by value, so
        a same-id workload from another tenant is rejected), else `KeyError`. A `request_id` still
        in-flight (deferred in the L2 gate) raises `ValueError` — reusing it would let the gate's
        idempotency short-circuit silently swallow this distinct request.
        """
        if self._workloads_by_id.get(workload.id) != workload:
            raise KeyError(
                f"workload {workload.id!r} is not in this stack's IR (group {self._group!r})"
            )
        if self._gate.is_pending(request_id):  # reject before charging L3, so nothing is lost
            raise ValueError(
                f"request_id {request_id!r} is already in-flight in the L2 gate — admit is "
                f"single-shot; give each request a unique id"
            )
        throttle = self._throttle.admit(self._group)
        if throttle is L3Decision.THROTTLE:
            return AdmitResult(throttle=throttle, admission=None)
        request = build_request(workload, request_id, arrival_ms)
        return AdmitResult(throttle=throttle, admission=self._gate.submit(request))

    def tick(self) -> Outcome | None:
        """Advance the L2 gate one wait-time transition (release or drop a deferred request)."""
        return self._gate.tick()

    def snapshot(self) -> dict[str, object]:
        """Combined observability: L2 gate metrics + L3 throttle metrics."""
        return {"l2": self._gate.metrics.snapshot(), "l3": self._throttle.snapshot()}


def build_admission_stack(
    ir: MissionIR,
    *,
    clock: Clock,
    load: LoadSignal,
    saturation: SaturationSignal,
    saturation_gate: SaturationGate,
    max_queue: int,
    ordering: OrderingKey | None = None,
    burst_seconds: float = 1.0,
) -> AdmissionStack:
    """Build the L2 gate + L3 throttle for `ir`'s tenant group from the same IR-derived policy.

    The L2 release ordering defaults to `slo_deadline` — matching the slo-deadline-ordering-policy
    that `render_l5` emits for this IR (every workload carries a deadline) — so the runtime honours
    the same deadline-aware scheduling the rendered/verified L5 mandates (ADR-0002). Pass `ordering`
    to override.
    """
    group = group_config_from_ir(ir, burst_seconds=burst_seconds)
    throttle = GroupThrottle(
        groups={group.name: group}, clock=clock, saturation=saturation, gate=saturation_gate
    )
    resolved = ORDERINGS["slo_deadline"] if ordering is None else ordering
    l2_gate = DeferredRedGate(clock=clock, load=load, max_queue=max_queue, ordering=resolved)
    return AdmissionStack(
        gate=l2_gate,
        throttle=throttle,
        group=group.name,
        workloads_by_id={w.id: w for w in ir.workloads},
    )
