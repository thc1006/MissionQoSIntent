"""Load-signal abstraction for the L2 gate: a protocol plus a scriptable in-memory stub.

The real `LoadSignal` (queue depth / KV-cache / running-reqs from the L1 inference engine) arrives
in a later, cluster-bound stage; here we ship the protocol plus a scriptable stub so the gate is
testable and replayable in isolation. The clock abstractions live in `mqi.runtime.clock`.
"""

from __future__ import annotations

from typing import Protocol


class LoadSignal(Protocol):
    """Live capacity and minimum-service-time estimate from the inference engine."""

    def available_slots(self) -> int: ...

    def estimate_min_service_ms(self) -> int: ...


class StaticLoad:
    """A scriptable in-memory `LoadSignal`: set `slots` / `min_service_ms` between cycles."""

    def __init__(self, *, slots: int = 0, min_service_ms: int = 0) -> None:
        self.slots = slots
        self.min_service_ms = min_service_ms

    def available_slots(self) -> int:
        return self.slots

    def estimate_min_service_ms(self) -> int:
        return self.min_service_ms
