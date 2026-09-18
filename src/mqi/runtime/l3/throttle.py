"""The L3 group throttle: a token bucket per group plus a tenant-group-aware saturation gate."""

from __future__ import annotations

from collections.abc import Mapping

from mqi.ir import MissionIR
from mqi.runtime.clock import Clock
from mqi.runtime.l3.bucket import TokenBucket
from mqi.runtime.l3.models import GroupConfig, L3Decision, L3Metrics
from mqi.runtime.l3.saturation import SaturationGate, SaturationSignal


class GroupThrottle:
    """Rate-limits requests per tenant group; sheds sheddable groups when the system saturates."""

    def __init__(
        self,
        *,
        groups: Mapping[str, GroupConfig],
        clock: Clock,
        saturation: SaturationSignal,
        gate: SaturationGate,
        metrics: L3Metrics | None = None,
    ) -> None:
        self._configs = dict(groups)
        self._buckets = {
            name: TokenBucket(rate_per_sec=c.rate_per_sec, burst=c.burst)
            for name, c in groups.items()
        }
        self._clock = clock
        self._saturation = saturation
        self._gate = gate
        self.metrics = metrics if metrics is not None else L3Metrics()

    def admit(self, group: str) -> L3Decision:
        """One decision for a request in `group`: PASS, or THROTTLE (saturation / rate).

        Under saturation the gate sheds sheddable groups but leaves protected groups to their
        guaranteed token rate — the tenant-group-aware difference from GAIE's global detector.
        Group isolation is inherent: each group draws only from its own bucket. `group` must be one
        configured at construction, else `KeyError` (fail-fast on an upstream misconfiguration).
        """
        if group not in self._configs:
            raise KeyError(f"unknown group {group!r}; configured: {sorted(self._configs)}")
        now = self._clock.now_ms()
        saturated = self._gate.update(self._saturation.level())
        if saturated and self._configs[group].sheddable:
            self.metrics.record_throttle(group, "saturation")
            return L3Decision.THROTTLE
        if self._buckets[group].try_consume(now):
            self.metrics.record_pass()
            return L3Decision.PASS
        self.metrics.record_throttle(group, "rate")
        return L3Decision.THROTTLE

    def token_levels(self) -> dict[str, float]:
        """Current per-group token levels (sorted; as of each bucket's last operation)."""
        return {name: self._buckets[name].level for name in sorted(self._buckets)}

    def snapshot(self) -> dict[str, object]:
        """Deterministic snapshot: tallies, reasons, per-group token levels, gate state."""
        return {
            "passed": self.metrics.passed,
            "throttled": self.metrics.throttled,
            "throttled_by_reason": dict(sorted(self.metrics.throttled_by_reason.items())),
            "throttled_by_group": dict(sorted(self.metrics.throttled_by_group.items())),
            "token_levels": self.token_levels(),
            "saturation_open": self._gate.is_open,
        }


def group_config_from_ir(ir: MissionIR, *, burst_seconds: float = 1.0) -> GroupConfig:
    """Derive the tenant group's throttle policy from the IR L3 targets.

    Rate = the sum of the group's workload throughput floors (`token_bucket_share`); burst = one
    `burst_seconds` window of that rate (min 1.0). The group is sheddable only when every workload
    is (`fallback == "shed"`), so a tenant with any guaranteed traffic stays protected.
    """
    if not ir.workloads:
        raise ValueError("cannot derive a group config from an IR with no workloads")
    rate = sum(w.targets.l3.token_bucket_share for w in ir.workloads)
    sheddable = all(w.fallback == "shed" for w in ir.workloads)
    return GroupConfig(
        name=ir.tenant,
        rate_per_sec=rate,
        burst=max(1.0, rate * burst_seconds),
        sheddable=sheddable,
    )
