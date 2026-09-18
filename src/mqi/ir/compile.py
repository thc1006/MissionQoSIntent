"""Compile a policy-validated contract into the typed IR."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from mqi.contracts import MissionQoSContract
from mqi.contracts.models import Workload
from mqi.ir.models import (
    IRWorkload,
    L1Target,
    L2Target,
    L3Target,
    L4Target,
    L5Target,
    LayerTargets,
    MissionIR,
    Provenance,
)
from mqi.policy import GuardDecision, PolicyDenied, evaluate

GuardFn = Callable[[dict[str, Any]], GuardDecision]

_PATH_SEGMENT = re.compile(r"^([A-Za-z_]\w*)(?:\[(\d+)\])?$")

# The five vLLM MSP metrics the L1 engine exports and L2 consumes (layers-L1-L5.md).
_VLLM_METRICS = (
    "vllm:num_requests_waiting",
    "vllm:num_requests_running",
    "vllm:kv_cache_usage_perc",
    "vllm:lora_requests_info",
    "vllm:cache_config_info",
)


def compile_ir(contract: MissionQoSContract, *, guard: GuardFn = evaluate) -> MissionIR:
    """Gate a contract through the policy guard, then compile it into the typed IR.

    Raises:
        PolicyDenied: if the guard denies the contract (carries the deny reasons).
    """
    decision = guard(contract.model_dump(mode="json", by_alias=True))
    if not decision.allowed:
        raise PolicyDenied(decision.reasons)
    return _build_ir(contract)


def resolve_contract_path(contract_json: dict[str, Any], path: str) -> Any:
    """Resolve a provenance path (e.g. ``spec.workloads[0]``) to its node in the contract JSON."""
    node: Any = contract_json
    for segment in path.split("."):
        match = _PATH_SEGMENT.match(segment)
        if match is None:
            raise KeyError(f"invalid provenance path segment: {segment!r}")
        node = node[match.group(1)]
        if match.group(2) is not None:
            node = node[int(match.group(2))]
    return node


def _build_ir(contract: MissionQoSContract) -> MissionIR:
    tenant = contract.metadata.tenant
    mission = contract.metadata.mission
    workloads = tuple(
        _build_workload(index, workload, tenant, mission)
        for index, workload in enumerate(contract.spec.workloads)
    )
    return MissionIR(tenant=tenant, mission=mission, workloads=workloads)


def _build_workload(index: int, workload: Workload, tenant: str, mission: str) -> IRWorkload:
    device_class = workload.resource_class
    deadline_ms = workload.slo.deadline_ms
    priority = workload.priority
    sheddable = str(workload.fallback) == "shed"
    targets = LayerTargets(
        l1=L1Target(device_class=device_class, metrics=_VLLM_METRICS),
        l2=L2Target(
            slack_basis_ms=deadline_ms,
            on_drop="drop" if sheddable else "reject",
            drop_relaxation=round(1.0 - workload.assurance_ratio, 6),
        ),
        l3=L3Target(
            group=tenant,
            token_bucket_share=workload.throughput_floor_rps or 0.0,
        ),
        l4=L4Target(
            priority_class_value=priority,
            device_class=device_class,
            reserved_ratio=workload.assurance_ratio,
        ),
        l5=L5Target(
            priority_band=priority,
            request_ttl_ms=deadline_ms,
            sheddable=sheddable,
            backend_class=device_class,
        ),
    )
    return IRWorkload(
        id=f"wl-{index}-{workload.mission_class}",
        mission_class=str(workload.mission_class),
        priority=priority,
        deadline_ms=deadline_ms,
        p99_latency_ms=workload.slo.p99_latency_ms,
        assurance_ratio=workload.assurance_ratio,
        device_class=device_class,
        throughput_floor_rps=workload.throughput_floor_rps,
        fallback=str(workload.fallback),
        targets=targets,
        provenance=Provenance(
            contract_field=f"spec.workloads[{index}]",
            mission_semantic=str(workload.mission_class),
            source=mission,
        ),
    )
