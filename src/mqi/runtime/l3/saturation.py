"""Saturation signal plus a hysteresis gate for throttling under system overload.

The signal is a scalar system-saturation level (e.g. vLLM KV-cache utilisation or normalised queue
depth — the inputs GAIE's utilization-detector uses). Unlike GAIE's single-threshold detector, the
gate here is hysteretic: it opens at `high` and only closes once the level falls back to `low`,
avoiding flap around the threshold.
"""

from __future__ import annotations

from typing import Protocol


class SaturationSignal(Protocol):
    """A scalar system-saturation level (KV-cache utilisation / normalised queue depth)."""

    def level(self) -> float: ...


class StaticSaturation:
    """A scriptable in-memory `SaturationSignal`: set `value` between cycles in a test/replay."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def level(self) -> float:
        return self.value


class SaturationGate:
    """A hysteresis gate: opens at `high`, closes at `low` (`high > low`), holds inside the band."""

    def __init__(self, *, high: float, low: float) -> None:
        if high <= low:
            raise ValueError(f"saturation gate needs high > low, got high={high}, low={low}")
        self._high = high
        self._low = low
        self._open = False

    def update(self, level: float) -> bool:
        """Feed the current level; return whether the gate is open after applying hysteresis."""
        if self._open:
            if level <= self._low:
                self._open = False
        elif level >= self._high:
            self._open = True
        return self._open

    @property
    def is_open(self) -> bool:
        return self._open
