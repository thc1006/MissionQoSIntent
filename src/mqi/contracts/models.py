"""Pydantic v2 models for the declarative mission/tenant QoS contract.

The authoritative schema is the SDD example (ir/mission-qos-contract.schema.example.md); field
names/types are defined here (the SDD defers the final schema to the implementation repo).
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic_core import PydanticCustomError

# Stage-1 heuristic ceiling for the Little's-law deadline<->throughput feasibility check
# (the authoritative capacity/quota gate is OPA, a later stage; see SDD FR-2).
MAX_INFLIGHT_PER_WORKLOAD = 1024


class MissionClass(StrEnum):
    """Mission class / criticality tier (the four SDD workload archetypes)."""

    EMERGENCY_ROUTING = "emergency-routing"
    INCIDENT_VERIFICATION = "incident-verification"
    CITY_MONITORING = "city-monitoring"
    HISTORICAL_ANALYSIS = "historical-analysis"


class Fallback(StrEnum):
    """Overload behaviour when the workload cannot be served within SLO."""

    REJECT_WITH_REASON = "reject-with-reason"
    DEGRADE_THEN_REJECT = "degrade-then-reject"
    DEGRADE = "degrade"
    SHED = "shed"


_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)(ms|s|m)\s*$")
_UNIT_TO_MS = {"ms": 1, "s": 1000, "m": 60_000}
_INVALID_DURATION_MSG = "duration must be a number or duration string"


def _parse_duration(value: object) -> int:
    """Coerce a human duration (``"500ms"``/``"2s"``/``"1m"``) or a bare int to milliseconds."""
    if isinstance(value, bool):  # bool is an int subclass; reject it explicitly
        raise PydanticCustomError("invalid_duration", _INVALID_DURATION_MSG)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        match = _DURATION_RE.match(value)
        if match is not None:
            return int(float(match.group(1)) * _UNIT_TO_MS[match.group(2)])
    raise PydanticCustomError(
        "invalid_duration",
        "invalid duration {value!r}; expected e.g. '500ms', '2s', '1m'",
        {"value": value},
    )


DurationMs = Annotated[int, BeforeValidator(_parse_duration)]

_MODEL_CONFIG = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
    strict=True,
    extra="forbid",
)


class ContractMetadata(BaseModel):
    """Ownership of the contract: which tenant and which mission it belongs to."""

    model_config = _MODEL_CONFIG

    tenant: str = Field(min_length=1)
    mission: str = Field(min_length=1)


class SLO(BaseModel):
    """Service-level objectives for a workload (end-to-end deadline + optional p99 latency)."""

    model_config = _MODEL_CONFIG

    deadline_ms: DurationMs = Field(alias="deadline", gt=0)
    p99_latency_ms: DurationMs | None = Field(default=None, alias="p99Latency", gt=0)

    @model_validator(mode="after")
    def _p99_within_deadline(self) -> SLO:
        if self.p99_latency_ms is not None and self.p99_latency_ms > self.deadline_ms:
            raise PydanticCustomError(
                "slo_incoherent",
                "p99Latency {p99}ms exceeds deadline {deadline}ms",
                {"p99": self.p99_latency_ms, "deadline": self.deadline_ms},
            )
        return self


class Workload(BaseModel):
    """A single mission workload and its compiled-into-QoS requirements."""

    model_config = _MODEL_CONFIG

    # strict=False on the enums and the float floor: YAML supplies their scalar value
    # (an enum's string value, or an int for the rps floor), not a typed instance.
    mission_class: MissionClass = Field(strict=False)
    priority: int = Field(ge=0)
    slo: SLO
    throughput_floor_rps: float | None = Field(default=None, gt=0, strict=False)
    resource_class: str = Field(min_length=1)
    assurance_ratio: float = Field(gt=0, le=1)
    fallback: Fallback = Field(strict=False)
    # DRA privileged "Admin Access" (GA in K8s v1.36); gated by the policy guard's R4.
    admin_access: bool = Field(default=False)

    @model_validator(mode="after")
    def _deadline_throughput_feasible(self) -> Workload:
        """Little's-law sanity: a throughput floor must be servable within the deadline.

        Required concurrency ``N = throughputFloorRps * deadlineMs / 1000`` must not exceed
        ``MAX_INFLIGHT_PER_WORKLOAD`` (a Stage-1 heuristic; the authoritative gate is OPA).
        """
        if self.throughput_floor_rps is None:
            return self
        required_inflight = self.throughput_floor_rps * self.slo.deadline_ms / 1000
        if required_inflight > MAX_INFLIGHT_PER_WORKLOAD:
            raise PydanticCustomError(
                "deadline_throughput_conflict",
                "throughputFloorRps {rps} with deadline {deadline}ms needs ~{needed} in-flight "
                "requests, exceeding MAX_INFLIGHT_PER_WORKLOAD {ceiling}",
                {
                    "rps": self.throughput_floor_rps,
                    "deadline": self.slo.deadline_ms,
                    "needed": int(required_inflight),
                    "ceiling": MAX_INFLIGHT_PER_WORKLOAD,
                },
            )
        return self


class ContractSpec(BaseModel):
    """The contract body: one or more mission workloads."""

    model_config = _MODEL_CONFIG

    workloads: list[Workload] = Field(min_length=1)


class MissionQoSContract(BaseModel):
    """A declarative multi-tenant QoS contract (`missionqos.dev/v0`)."""

    model_config = _MODEL_CONFIG

    api_version: Literal["missionqos.dev/v0"]
    kind: Literal["MissionQoSContract"]
    metadata: ContractMetadata
    spec: ContractSpec
