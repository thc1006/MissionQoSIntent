"""Typed IR models: an immutable, hashable single source of truth compiled from a contract."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

_FROZEN = ConfigDict(frozen=True)


class Provenance(BaseModel):
    """Back-link from an IR node to the contract field and mission semantic that produced it."""

    model_config = _FROZEN

    contract_field: str
    mission_semantic: str
    source: str


class L1Target(BaseModel):
    """L1 inference engine (external): the device it binds to + the metrics it exports."""

    model_config = _FROZEN

    device_class: str
    metrics: tuple[str, ...]


class L2Target(BaseModel):
    """L2 request-level admission (deferred-red gate)."""

    model_config = _FROZEN

    slack_basis_ms: int
    on_drop: Literal["reject", "drop"]
    drop_relaxation: float


class L3Target(BaseModel):
    """L3 group throttling (GroupTB / saturation)."""

    model_config = _FROZEN

    group: str
    token_bucket_share: float


class L4Target(BaseModel):
    """L4 quota & devices (Kueue WorkloadPriorityClass + DRA DeviceClass)."""

    model_config = _FROZEN

    priority_class_value: int
    device_class: str
    reserved_ratio: float


class L5Target(BaseModel):
    """L5 gateway (GAIE priority band + request TTL + sheddability)."""

    model_config = _FROZEN

    priority_band: int
    request_ttl_ms: int
    sheddable: bool
    backend_class: str


class LayerTargets(BaseModel):
    """The L1-L5 targets derived from one workload."""

    model_config = _FROZEN

    l1: L1Target
    l2: L2Target
    l3: L3Target
    l4: L4Target
    l5: L5Target


class IRWorkload(BaseModel):
    """A normalized, layer-annotated IR node for one mission workload."""

    model_config = _FROZEN

    id: str
    mission_class: str
    priority: int
    deadline_ms: int
    p99_latency_ms: int | None
    assurance_ratio: float
    device_class: str
    throughput_floor_rps: float | None
    fallback: str
    targets: LayerTargets
    provenance: Provenance

    @model_validator(mode="after")
    def _consistent(self) -> IRWorkload:
        """Enforce the cross-layer alignment invariants (docs/architecture/layers-L1-L5.md)."""
        t = self.targets
        problems: list[str] = []
        if not (t.l2.slack_basis_ms == self.deadline_ms == t.l5.request_ttl_ms):
            problems.append("deadline (L2 slack / L5 ttl)")
        if not (t.l4.priority_class_value == self.priority == t.l5.priority_band):
            problems.append("priority (L4 class / L5 band)")
        if not (t.l1.device_class == self.device_class == t.l4.device_class == t.l5.backend_class):
            problems.append("device_class (L1/L4/L5)")
        sheddable = self.fallback == "shed"
        if (t.l5.sheddable != sheddable) or ((t.l2.on_drop == "drop") != sheddable):
            problems.append("fallback (L2 drop / L5 sheddable)")
        if problems:
            raise ValueError(f"IR workload {self.id!r} targets inconsistent: {', '.join(problems)}")
        return self


class MissionIR(BaseModel):
    """The compiled typed IR for a mission contract (single source of truth)."""

    model_config = _FROZEN

    ir_version: str = "0.1.0"
    tenant: str
    mission: str
    workloads: tuple[IRWorkload, ...]

    @property
    def content_hash(self) -> str:
        """Stable sha256 hex over the canonical JSON of this IR (deterministic; excludes itself)."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
