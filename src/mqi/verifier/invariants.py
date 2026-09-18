"""Cross-layer invariants: each checker returns the violations it finds (empty = held)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mqi.ir import MissionIR
from mqi.verifier.bundle import RenderedBundle
from mqi.verifier.models import Violation

Checker = Callable[[MissionIR, RenderedBundle], list[Violation]]


def _epp_flow_control(bundle: RenderedBundle) -> dict[str, Any]:
    epps = bundle.l5_of_kind("EndpointPickerConfig")
    if not epps:
        return {}
    flow_control: dict[str, Any] = epps[0].get("flowControl", {})
    return flow_control


def _priority_bands(bundle: RenderedBundle) -> list[dict[str, Any]]:
    bands: list[dict[str, Any]] = _epp_flow_control(bundle).get("priorityBands", [])
    return bands


def _l2_gates(bundle: RenderedBundle) -> list[dict[str, Any]]:
    spec: dict[str, Any] = bundle.l2.get("spec", {})
    gates: list[dict[str, Any]] = spec.get("gates", [])
    return gates


def _bijection_violations(
    layer: str, ir_priorities: set[int], actual: list[Any]
) -> list[Violation]:
    violations: list[Violation] = []
    actual_set = set(actual)
    for priority in sorted(ir_priorities - actual_set):
        violations.append(Violation(
            invariant="priority_band_bijection",
            subject=f"priority {priority}",
            expected=f"exactly one {layer} = {priority}",
            actual="missing",
            detail=f"IR priority {priority} has no matching {layer}",
        ))
    for value in sorted(actual_set - ir_priorities):
        violations.append(Violation(
            invariant="priority_band_bijection",
            subject=f"priority {value}",
            expected="a priority present in the IR",
            actual=f"{layer} = {value}",
            detail=f"{layer} {value} does not correspond to any IR priority",
        ))
    for value in sorted({v for v in actual if actual.count(v) > 1}):
        violations.append(Violation(
            invariant="priority_band_bijection",
            subject=f"priority {value}",
            expected=f"exactly one {layer} = {value}",
            actual=f"{actual.count(value)} entries",
            detail=f"{layer} has duplicate priority {value}",
        ))
    return violations


def check_priority_band_bijection(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Every IR priority maps to exactly one Kueue priority class and one GAIE priorityBand."""
    ir_priorities = {w.priority for w in ir.workloads}
    l4_values = [wpc.get("value") for wpc in bundle.l4_of_kind("WorkloadPriorityClass")]
    l5_values = [band.get("priority") for band in _priority_bands(bundle)]
    return _bijection_violations(
        "L4 WorkloadPriorityClass value", ir_priorities, l4_values
    ) + _bijection_violations("L5 priorityBand priority", ir_priorities, l5_values)


_DEADLINE_AWARE_ORDERING = {"edf-ordering-policy", "slo-deadline-ordering-policy"}


def check_deadline_aware_ordering(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Every L5 band must use a deadline-aware ordering policy (all IR workloads have deadlines)."""
    violations: list[Violation] = []
    for band in _priority_bands(bundle):
        policy = band.get("orderingPolicyRef")
        if policy not in _DEADLINE_AWARE_ORDERING:
            violations.append(Violation(
                invariant="deadline_aware_ordering",
                subject=f"L5 priorityBand {band.get('priority')}",
                expected="edf-ordering-policy or slo-deadline-ordering-policy",
                actual=str(policy),
                detail=f"L5 band {band.get('priority')} uses non-deadline ordering {policy!r}",
            ))
    return violations


def check_deadline_slack_alignment(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """L2 gate slackBasisMs == IR deadline (per workload); L5 defaultRequestTTL == max deadline."""
    violations: list[Violation] = []
    slack_by_workload = {g.get("workload"): g.get("slackBasisMs") for g in _l2_gates(bundle)}
    for workload in ir.workloads:
        slack = slack_by_workload.get(workload.id)
        if slack != workload.deadline_ms:
            violations.append(Violation(
                invariant="deadline_slack_alignment",
                subject=workload.id,
                expected=f"slackBasisMs = {workload.deadline_ms}",
                actual=str(slack),
                detail=f"L2 slackBasisMs for {workload.id} is {slack}, not {workload.deadline_ms}",
            ))
    expected_ttl = f"{max(w.deadline_ms for w in ir.workloads)}ms"
    actual_ttl = _epp_flow_control(bundle).get("defaultRequestTTL")
    if actual_ttl != expected_ttl:
        violations.append(Violation(
            invariant="deadline_slack_alignment",
            subject="L5 defaultRequestTTL",
            expected=expected_ttl,
            actual=str(actual_ttl),
            detail=f"L5 defaultRequestTTL is {actual_ttl!r}, expected {expected_ttl!r}",
        ))
    return violations


def _cluster_queue_quota(bundle: RenderedBundle) -> dict[str, Any]:
    quota: dict[str, Any] = {}
    for cq in bundle.l4_of_kind("ClusterQueue"):
        for group in cq.get("spec", {}).get("resourceGroups", []):
            for flavor in group.get("flavors", []):
                for resource in flavor.get("resources", []):
                    quota[resource.get("name")] = resource.get("nominalQuota", 0)
    return quota


def check_device_class_quota_coverage(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Each IR device class has an L4 ResourceFlavor and ClusterQueue nominalQuota >= demand."""
    violations: list[Violation] = []
    ir_classes = sorted({w.device_class for w in ir.workloads})
    demand = {dc: sum(w.device_class == dc for w in ir.workloads) for dc in ir_classes}
    flavor_names = {
        rf.get("metadata", {}).get("name") for rf in bundle.l4_of_kind("ResourceFlavor")
    }
    quota = _cluster_queue_quota(bundle)
    for dc in ir_classes:
        if dc not in flavor_names:
            violations.append(Violation(
                invariant="device_class_quota_coverage",
                subject=dc,
                expected=f"an L4 ResourceFlavor named {dc}",
                actual="missing",
                detail=f"IR device class {dc} has no L4 ResourceFlavor",
            ))
        available = quota.get(dc, 0)
        if available < demand[dc]:
            violations.append(Violation(
                invariant="device_class_quota_coverage",
                subject=dc,
                expected=f"nominalQuota >= {demand[dc]}",
                actual=str(available),
                detail=f"L4 nominalQuota {available} < demand {demand[dc]} for {dc}",
            ))
    return violations


def check_fallback_ondrop_alignment(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Each L2 gate's onDrop must equal the IR workload's fallback (shed -> drop semantics)."""
    violations: list[Violation] = []
    ondrop_by_workload = {g.get("workload"): g.get("onDrop") for g in _l2_gates(bundle)}
    for workload in ir.workloads:
        actual = ondrop_by_workload.get(workload.id)
        if actual != workload.fallback:
            violations.append(Violation(
                invariant="fallback_ondrop_alignment",
                subject=workload.id,
                expected=f"onDrop = {workload.fallback}",
                actual=str(actual),
                detail=f"L2 onDrop for {workload.id} is {actual!r}, expected {workload.fallback!r}",
            ))
    return violations


def _first(items: list[dict[str, Any]]) -> dict[str, Any]:
    return items[0] if items else {}


def check_tenant_mission_consistency(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Every tenant/mission-derived name in the artifacts matches the IR tenant/mission.

    Artifact-level identity/attribution; the absolute entitlement *cap* is the Stage-2 guard's job.
    """
    tenant, mission = ir.tenant, ir.mission
    cq = _first(bundle.l4_of_kind("ClusterQueue"))
    cohort = _first(bundle.l4_of_kind("Cohort"))
    lq = _first(bundle.l4_of_kind("LocalQueue"))
    pool = _first(bundle.l5_of_kind("InferencePool"))
    checks: list[tuple[str, Any, str]] = [
        ("L2 metadata.tenant", bundle.l2.get("metadata", {}).get("tenant"), tenant),
        ("L2 metadata.name", bundle.l2.get("metadata", {}).get("name"), mission),
        ("L4 ClusterQueue.name", cq.get("metadata", {}).get("name"), f"{tenant}-cq"),
        ("L4 ClusterQueue.cohortName", cq.get("spec", {}).get("cohortName"), f"{tenant}-cohort"),
        ("L4 Cohort.name", cohort.get("metadata", {}).get("name"), f"{tenant}-cohort"),
        ("L4 LocalQueue.name", lq.get("metadata", {}).get("name"), f"{tenant}-lq"),
        ("L4 LocalQueue.namespace", lq.get("metadata", {}).get("namespace"), tenant),
        ("L4 LocalQueue.clusterQueue", lq.get("spec", {}).get("clusterQueue"), f"{tenant}-cq"),
        ("L5 InferencePool.name", pool.get("metadata", {}).get("name"), f"{mission}-pool"),
        (
            "L5 InferencePool.endpointPickerRef",
            pool.get("spec", {}).get("endpointPickerRef", {}).get("name"),
            f"{mission}-epp",
        ),
    ]
    for template in bundle.l4_of_kind("ResourceClaimTemplate"):
        ns = template.get("metadata", {}).get("namespace")
        checks.append(("L4 ResourceClaimTemplate.namespace", ns, tenant))
    violations: list[Violation] = []
    for subject, actual, expected in checks:
        if actual != expected:
            violations.append(Violation(
                invariant="tenant_mission_consistency",
                subject=subject,
                expected=expected,
                actual=str(actual),
                detail=f"{subject} {actual!r} != {expected!r}",
            ))
    return violations


def check_no_spurious_l2_gates(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Every L2 gate must reference an IR workload (no spurious gate for an absent workload)."""
    ir_ids = {w.id for w in ir.workloads}
    violations: list[Violation] = []
    for gate in _l2_gates(bundle):
        workload_id = gate.get("workload")
        if workload_id not in ir_ids:
            violations.append(Violation(
                invariant="no_spurious_l2_gates",
                subject=str(workload_id),
                expected="a workload present in the IR",
                actual=f"L2 gate for {workload_id}",
                detail=f"L2 gate references workload {workload_id!r} not in the IR",
            ))
    return violations


def _metadata_name(obj: dict[str, Any]) -> Any:
    return obj.get("metadata", {}).get("name")


def check_l4_device_references_resolve(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Every device-class reference in the L4 manifests resolves to an IR device class.

    Covers ResourceFlavor/DeviceClass names, ClusterQueue coveredResources + flavor/resource names,
    and ResourceClaimTemplate.spec.spec.devices.requests[].exactly.deviceClassName (nested, v1 DRA).
    """
    ir_classes = {w.device_class for w in ir.workloads}
    references: list[tuple[str, Any]] = []
    for flavor in bundle.l4_of_kind("ResourceFlavor"):
        references.append(("ResourceFlavor.name", _metadata_name(flavor)))
    for device_class in bundle.l4_of_kind("DeviceClass"):
        references.append(("DeviceClass.name", _metadata_name(device_class)))
    for cq in bundle.l4_of_kind("ClusterQueue"):
        for group in cq.get("spec", {}).get("resourceGroups", []):
            for covered in group.get("coveredResources", []):
                references.append(("ClusterQueue.coveredResources", covered))
            for flavor in group.get("flavors", []):
                references.append(("ClusterQueue.flavor.name", flavor.get("name")))
                for resource in flavor.get("resources", []):
                    references.append(("ClusterQueue.resource.name", resource.get("name")))
    for template in bundle.l4_of_kind("ResourceClaimTemplate"):
        requests = template.get("spec", {}).get("spec", {}).get("devices", {}).get("requests", [])
        for request in requests:
            device = request.get("exactly", {}).get("deviceClassName")
            references.append(("ResourceClaimTemplate.deviceClassName", device))
    violations: list[Violation] = []
    for path, token in references:
        if token not in ir_classes:
            violations.append(Violation(
                invariant="l4_device_references_resolve",
                subject=str(token),
                expected="a device class present in the IR",
                actual=f"{path} = {token}",
                detail=f"L4 {path} {token!r} does not resolve to an IR device class",
            ))
    return violations


def check_singleton_control_objects(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Exactly one of each cluster-scoped control object (no duplicate or missing objects)."""
    counts = (
        ("Cohort", len(bundle.l4_of_kind("Cohort"))),
        ("ClusterQueue", len(bundle.l4_of_kind("ClusterQueue"))),
        ("LocalQueue", len(bundle.l4_of_kind("LocalQueue"))),
        ("InferencePool", len(bundle.l5_of_kind("InferencePool"))),
        ("EndpointPickerConfig", len(bundle.l5_of_kind("EndpointPickerConfig"))),
    )
    violations: list[Violation] = []
    for kind, count in counts:
        if count != 1:
            violations.append(Violation(
                invariant="singleton_control_objects",
                subject=kind,
                expected=f"exactly one {kind}",
                actual=str(count),
                detail=f"expected exactly one {kind}, found {count}",
            ))
    return violations


def check_no_duplicate_named_objects(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Within each L4/L5 kind, metadata.name must be unique (no duplicate objects)."""
    violations: list[Violation] = []
    for objects in (bundle.l4, bundle.l5):
        names_by_kind: dict[Any, list[Any]] = {}
        for obj in objects:
            names_by_kind.setdefault(obj.get("kind"), []).append(_metadata_name(obj))
        for kind, names in names_by_kind.items():
            duplicates = sorted({n for n in names if n is not None and names.count(n) > 1})
            for name in duplicates:
                violations.append(Violation(
                    invariant="no_duplicate_named_objects",
                    subject=f"{kind}/{name}",
                    expected=f"a unique metadata.name within {kind}",
                    actual=f"{names.count(name)} objects named {name}",
                    detail=f"{names.count(name)} {kind} objects share metadata.name {name!r}",
                ))
    return violations


def check_intra_bundle_references_resolve(ir: MissionIR, bundle: RenderedBundle) -> list[Violation]:
    """Cross-object references resolve to an object in the bundle (no dangling links)."""
    cq_names = {_metadata_name(o) for o in bundle.l4_of_kind("ClusterQueue")}
    cohort_names = {_metadata_name(o) for o in bundle.l4_of_kind("Cohort")}
    dc_names = {_metadata_name(o) for o in bundle.l4_of_kind("DeviceClass")}
    references: list[tuple[str, Any, set[Any]]] = []
    for local_queue in bundle.l4_of_kind("LocalQueue"):
        references.append(
            ("LocalQueue.clusterQueue", local_queue.get("spec", {}).get("clusterQueue"), cq_names)
        )
    for cluster_queue in bundle.l4_of_kind("ClusterQueue"):
        cohort_ref = cluster_queue.get("spec", {}).get("cohortName")
        references.append(("ClusterQueue.cohortName", cohort_ref, cohort_names))
    for template in bundle.l4_of_kind("ResourceClaimTemplate"):
        requests = template.get("spec", {}).get("spec", {}).get("devices", {}).get("requests", [])
        for request in requests:
            target = request.get("exactly", {}).get("deviceClassName")
            references.append(("ResourceClaimTemplate.deviceClassName", target, dc_names))
    violations: list[Violation] = []
    for desc, target, valid in references:
        if target not in valid:
            violations.append(Violation(
                invariant="intra_bundle_references_resolve",
                subject=str(target),
                expected=f"an existing object referenced by {desc}",
                actual=f"{desc} = {target}",
                detail=f"{desc} {target!r} does not resolve to an object in the bundle",
            ))
    return violations


# Scope: these invariants check IR-derived cross-layer alignment, artifact minimality, intra-bundle
# reference integrity, and tenant/mission attribution. FIXED rendering constants (fairnessPolicyRef,
# saturationDetector params, apiVersions, selector/targetPorts, nodeLabels, WPC name<->value
# formatting) are out of scope here: Stage-4 golden byte-equality pins them, Stage-9 kubeconform
# validates the CRD schemas.
INVARIANTS: tuple[tuple[str, Checker], ...] = (
    ("priority_band_bijection", check_priority_band_bijection),
    ("deadline_aware_ordering", check_deadline_aware_ordering),
    ("deadline_slack_alignment", check_deadline_slack_alignment),
    ("device_class_quota_coverage", check_device_class_quota_coverage),
    ("fallback_ondrop_alignment", check_fallback_ondrop_alignment),
    ("tenant_mission_consistency", check_tenant_mission_consistency),
    ("no_spurious_l2_gates", check_no_spurious_l2_gates),
    ("l4_device_references_resolve", check_l4_device_references_resolve),
    ("singleton_control_objects", check_singleton_control_objects),
    ("no_duplicate_named_objects", check_no_duplicate_named_objects),
    ("intra_bundle_references_resolve", check_intra_bundle_references_resolve),
)
