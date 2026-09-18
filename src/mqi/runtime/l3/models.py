"""Value types for L3 group throttling: decision, per-group config, metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(frozen=True)


class L3Decision(StrEnum):
    """The two L3 outcomes — no DROP: a throttled request is rate-limited, not killed."""

    PASS = "pass"
    THROTTLE = "throttle"


class GroupConfig(BaseModel):
    """Per-group throttling policy: guaranteed rate, burst capacity, and sheddability."""

    model_config = _FROZEN

    name: str
    rate_per_sec: float
    burst: float
    sheddable: bool = False


@dataclass
class L3Metrics:
    """Mutable L3 counters: pass/throttle tallies with throttle reasons and per-group breakdown."""

    passed: int = 0
    throttled: int = 0
    throttled_by_reason: dict[str, int] = field(default_factory=dict)
    throttled_by_group: dict[str, int] = field(default_factory=dict)

    def record_pass(self) -> None:
        self.passed += 1

    def record_throttle(self, group: str, reason: str) -> None:
        self.throttled += 1
        self.throttled_by_reason[reason] = self.throttled_by_reason.get(reason, 0) + 1
        self.throttled_by_group[group] = self.throttled_by_group.get(group, 0) + 1
