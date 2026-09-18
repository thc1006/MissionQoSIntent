"""A monotonic-clock token bucket: exact refill, burst up to capacity."""

from __future__ import annotations


class TokenBucket:
    """A token bucket refilling at `rate_per_sec` up to `burst` tokens; starts full.

    Time comes from the caller in milliseconds, so refill is exact under a fake clock:
    `tokens = min(burst, tokens + rate_per_sec * elapsed_ms / 1000)`.
    """

    def __init__(self, *, rate_per_sec: float, burst: float, tokens: float | None = None) -> None:
        if rate_per_sec < 0:
            raise ValueError(f"rate_per_sec must be >= 0, got {rate_per_sec}")
        if burst < 0:
            raise ValueError(f"burst must be >= 0, got {burst}")
        self.rate_per_sec = rate_per_sec
        self.burst = burst
        self._tokens = burst if tokens is None else tokens
        self._last_ms: int | None = None

    def _refill(self, now_ms: int) -> None:
        if self._last_ms is None:
            self._last_ms = now_ms
            return
        elapsed_ms = now_ms - self._last_ms
        if elapsed_ms <= 0:
            return
        self._tokens = min(self.burst, self._tokens + self.rate_per_sec * elapsed_ms / 1000.0)
        self._last_ms = now_ms

    def try_consume(self, now_ms: int, n: float = 1.0) -> bool:
        """Refill to `now_ms`, then consume `n` (>= 0) tokens if available; report success."""
        if n < 0:
            raise ValueError(f"cannot consume a negative number of tokens, got {n}")
        self._refill(now_ms)
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False

    @property
    def level(self) -> float:
        """Current token count (as of the last refill)."""
        return self._tokens
