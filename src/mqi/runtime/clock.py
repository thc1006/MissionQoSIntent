"""Deterministic clock abstractions shared by the runtime mechanisms (L2 gate, L3 throttle).

A `Clock` is a millisecond monotonic time source. `ManualClock` is hand-advanced for unit tests and
E3 replay; `SystemClock` reads the monotonic system timer in production.
"""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    """A source of monotonic wall-clock time in milliseconds."""

    def now_ms(self) -> int: ...


class ManualClock:
    """A deterministic, hand-advanced clock (unit tests and E3 replay)."""

    def __init__(self, now_ms: int = 0) -> None:
        self._now_ms = now_ms

    def now_ms(self) -> int:
        return self._now_ms

    def advance(self, delta_ms: int) -> None:
        self._now_ms += delta_ms

    def set(self, now_ms: int) -> None:
        self._now_ms = now_ms


class SystemClock:
    """Wall-clock milliseconds from the monotonic system timer (production default)."""

    def now_ms(self) -> int:
        return time.monotonic_ns() // 1_000_000
