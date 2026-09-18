"""Cross-layer consistency verifier: consistent bundle passes; each invariant is falsifiable."""

import yaml

from mqi.ir import MissionIR
from mqi.verifier import verify


def test_consistent_bundle_passes(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered

    report = verify(ir, l2=l2, l4=l4, l5=l5)

    assert report.ok
    assert "priority_band_bijection" in report.proven
    assert "deadline_aware_ordering" in report.proven
    assert "deadline_slack_alignment" in report.proven
    assert "device_class_quota_coverage" in report.proven
    assert "fallback_ondrop_alignment" in report.proven
    assert "tenant_mission_consistency" in report.proven
    assert "no_spurious_l2_gates" in report.proven
    assert "l4_device_references_resolve" in report.proven
    assert "singleton_control_objects" in report.proven
    assert "no_duplicate_named_objects" in report.proven
    assert "intra_bundle_references_resolve" in report.proven
    assert report.violations == ()
    assert len(report.proven) == 11


def test_report_is_deterministic(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    assert verify(ir, l2=l2, l4=l4, l5=l5) == verify(ir, l2=l2, l4=l4, l5=l5)


def test_report_is_machine_readable(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered

    dumped = verify(ir, l2=l2, l4=l4, l5=l5).model_dump()

    assert dumped["ok"] is True
    assert isinstance(dumped["proven"], tuple)
    assert dumped["violations"] == ()


def test_falsify_priority_band_bijection(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l5 = l5.replace("priority: 100", "priority: 99")  # L5 band no longer matches the IR

    report = verify(ir, l2=l2, l4=l4, l5=bad_l5)

    assert report.ok is False
    assert "priority_band_bijection" not in report.proven
    hits = [v for v in report.violations if v.invariant == "priority_band_bijection"]
    assert hits and all(v.detail for v in hits)


def test_falsify_deadline_aware_ordering(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l5 = l5.replace("slo-deadline-ordering-policy", "fcfs-ordering-policy", 1)

    report = verify(ir, l2=l2, l4=l4, l5=bad_l5)

    assert report.ok is False
    assert "deadline_aware_ordering" not in report.proven
    assert any(v.invariant == "deadline_aware_ordering" for v in report.violations)
    assert "priority_band_bijection" in report.proven  # one mismatch => one failing invariant


def test_falsify_deadline_slack_alignment(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l2 = l2.replace("slackBasisMs: 500", "slackBasisMs: 501")

    report = verify(ir, l2=bad_l2, l4=l4, l5=l5)

    assert report.ok is False
    assert "deadline_slack_alignment" not in report.proven
    assert any(v.invariant == "deadline_slack_alignment" for v in report.violations)
    assert "priority_band_bijection" in report.proven


def test_falsify_l5_request_ttl(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l5 = l5.replace("defaultRequestTTL: 60000ms", "defaultRequestTTL: 500ms")

    report = verify(ir, l2=l2, l4=l4, l5=bad_l5)

    assert report.ok is False
    assert any(
        v.invariant == "deadline_slack_alignment" and v.subject == "L5 defaultRequestTTL"
        for v in report.violations
    )


def test_falsify_device_class_quota(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l4 = l4.replace("nominalQuota: 1", "nominalQuota: 0")  # gpu-40g quota 0 < demand 1

    report = verify(ir, l2=l2, l4=bad_l4, l5=l5)

    assert report.ok is False
    assert "device_class_quota_coverage" not in report.proven
    assert any(v.invariant == "device_class_quota_coverage" for v in report.violations)
    assert "priority_band_bijection" in report.proven


def test_falsify_device_class_coverage(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l4 = l4.replace("name: gpu-40g", "name: gpu-99g", 1)  # drop the gpu-40g ResourceFlavor

    report = verify(ir, l2=l2, l4=bad_l4, l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "device_class_quota_coverage" and "gpu-40g" in v.subject
        for v in report.violations
    )


def test_falsify_fallback_ondrop_alignment(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l2 = l2.replace("onDrop: shed", "onDrop: reject-with-reason")  # != IR fallback 'shed'

    report = verify(ir, l2=bad_l2, l4=l4, l5=l5)

    assert report.ok is False
    assert "fallback_ondrop_alignment" not in report.proven
    assert any(v.invariant == "fallback_ondrop_alignment" for v in report.violations)
    assert "priority_band_bijection" in report.proven


def test_falsify_tenant_consistency_l2(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l2 = l2.replace("tenant: ops-admin", "tenant: evil")

    report = verify(ir, l2=bad_l2, l4=l4, l5=l5)

    assert report.ok is False
    assert "tenant_mission_consistency" not in report.proven
    assert any(
        v.invariant == "tenant_mission_consistency" and v.subject == "L2 metadata.tenant"
        for v in report.violations
    )


def test_falsify_tenant_mission_l4_l5(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l4 = l4.replace("namespace: ops-admin", "namespace: evil", 1)  # LocalQueue namespace
    bad_l5 = l5.replace("name: urban-edge-2026-pool", "name: evil-pool")

    report = verify(ir, l2=l2, l4=bad_l4, l5=bad_l5)

    assert report.ok is False
    subjects = {v.subject for v in report.violations if v.invariant == "tenant_mission_consistency"}
    assert subjects == {"L4 LocalQueue.namespace", "L5 InferencePool.name"}


def test_falsify_duplicate_priority_band(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    bad_l5 = l5.replace("priority: 10", "priority: 50")  # band 50 duplicated, 10 dropped

    report = verify(ir, l2=l2, l4=l4, l5=bad_l5)

    assert report.ok is False
    assert any(
        v.invariant == "priority_band_bijection" and "duplicate" in v.detail
        for v in report.violations
    )


def test_verify_tolerates_degenerate_l5(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, _ = rendered

    report = verify(ir, l2=l2, l4=l4, l5="")  # no L5 documents at all

    assert report.ok is False
    assert report.violations  # reported, not crashed


def test_falsify_spurious_l2_gate(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    doc = yaml.safe_load(l2)
    doc["spec"]["gates"].append({
        "workload": "wl-99-ghost",
        "slackBasisMs": 1,
        "minServiceTimeSource": "metrics",
        "dropWhen": "x",
        "onDrop": "shed",
    })
    bad_l2 = yaml.safe_dump(doc)

    report = verify(ir, l2=bad_l2, l4=l4, l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "no_spurious_l2_gates" and "wl-99-ghost" in v.subject
        for v in report.violations
    )


def test_falsify_extra_device_flavor(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    docs = [d for d in yaml.safe_load_all(l4) if d is not None]
    docs.append({
        "apiVersion": "kueue.x-k8s.io/v1beta2",
        "kind": "ResourceFlavor",
        "metadata": {"name": "gpu-evil"},
        "spec": {},
    })
    bad_l4 = yaml.safe_dump_all(docs)

    report = verify(ir, l2=l2, l4=bad_l4, l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "l4_device_references_resolve" and "gpu-evil" in v.subject
        for v in report.violations
    )


def test_falsify_duplicate_cluster_queue(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    docs = [d for d in yaml.safe_load_all(l4) if d is not None]
    docs.append({
        "apiVersion": "kueue.x-k8s.io/v1beta2",
        "kind": "ClusterQueue",
        "metadata": {"name": "evil-cq"},
        "spec": {},
    })
    bad_l4 = yaml.safe_dump_all(docs)

    report = verify(ir, l2=l2, l4=bad_l4, l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "singleton_control_objects" and v.subject == "ClusterQueue"
        for v in report.violations
    )


def test_falsify_resource_claim_template_device_class(
    ir: MissionIR, rendered: tuple[str, str, str]
) -> None:
    l2, l4, l5 = rendered
    docs = [d for d in yaml.safe_load_all(l4) if d is not None]
    for doc in docs:
        if doc.get("kind") == "ResourceClaimTemplate":
            doc["spec"]["spec"]["devices"]["requests"][0]["exactly"]["deviceClassName"] = "gpu-evil"
            break
    bad_l4 = yaml.safe_dump_all(docs)

    report = verify(ir, l2=l2, l4=bad_l4, l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "l4_device_references_resolve" and "gpu-evil" in v.subject
        for v in report.violations
    )


def test_falsify_duplicate_resource_flavor(
    ir: MissionIR, rendered: tuple[str, str, str]
) -> None:
    l2, l4, l5 = rendered
    docs = [d for d in yaml.safe_load_all(l4) if d is not None]
    flavor = next(d for d in docs if d.get("kind") == "ResourceFlavor")
    docs.append({
        "apiVersion": flavor["apiVersion"],
        "kind": "ResourceFlavor",
        "metadata": {"name": flavor["metadata"]["name"]},  # duplicate name
        "spec": {},
    })
    bad_l4 = yaml.safe_dump_all(docs)

    report = verify(ir, l2=l2, l4=bad_l4, l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "no_duplicate_named_objects" and v.subject.startswith("ResourceFlavor/")
        for v in report.violations
    )


def _mutate_l4(l4: str, kind: str, fn: object) -> str:
    docs = [d for d in yaml.safe_load_all(l4) if d is not None]
    for doc in docs:
        if doc.get("kind") == kind:
            fn(doc)  # type: ignore[operator]
            break
    return yaml.safe_dump_all(docs)


def test_falsify_dangling_localqueue_clusterqueue(
    ir: MissionIR, rendered: tuple[str, str, str]
) -> None:
    l2, l4, l5 = rendered

    def _break(doc: object) -> None:
        doc["spec"]["clusterQueue"] = "nonexistent-cq"  # type: ignore[index]

    report = verify(ir, l2=l2, l4=_mutate_l4(l4, "LocalQueue", _break), l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "intra_bundle_references_resolve" and "nonexistent-cq" in v.subject
        for v in report.violations
    )


def test_falsify_dangling_clusterqueue_cohort(
    ir: MissionIR, rendered: tuple[str, str, str]
) -> None:
    l2, l4, l5 = rendered

    def _break(doc: object) -> None:
        doc["spec"]["cohortName"] = "nonexistent-cohort"  # type: ignore[index]

    report = verify(ir, l2=l2, l4=_mutate_l4(l4, "ClusterQueue", _break), l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "intra_bundle_references_resolve" and "nonexistent-cohort" in v.subject
        for v in report.violations
    )


def test_falsify_missing_device_class_dangles_claim_template(
    ir: MissionIR, rendered: tuple[str, str, str]
) -> None:
    l2, l4, l5 = rendered
    docs = [
        d for d in yaml.safe_load_all(l4) if d is not None and d.get("kind") != "DeviceClass"
    ]

    report = verify(ir, l2=l2, l4=yaml.safe_dump_all(docs), l5=l5)

    assert report.ok is False
    assert any(v.invariant == "intra_bundle_references_resolve" for v in report.violations)


def test_falsify_claim_template_namespace(
    ir: MissionIR, rendered: tuple[str, str, str]
) -> None:
    l2, l4, l5 = rendered

    def _break(doc: object) -> None:
        doc["metadata"]["namespace"] = "wrong-tenant"  # type: ignore[index]

    report = verify(ir, l2=l2, l4=_mutate_l4(l4, "ResourceClaimTemplate", _break), l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "tenant_mission_consistency"
        and v.subject == "L4 ResourceClaimTemplate.namespace"
        for v in report.violations
    )


def test_falsify_endpoint_picker_ref(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    pools = [d for d in yaml.safe_load_all(l5) if d is not None]
    for doc in pools:
        if doc.get("kind") == "InferencePool":
            doc["spec"]["endpointPickerRef"]["name"] = "evil-epp"
            break
    bad_l5 = yaml.safe_dump_all(pools)

    report = verify(ir, l2=l2, l4=l4, l5=bad_l5)

    assert report.ok is False
    assert any(
        v.invariant == "tenant_mission_consistency"
        and v.subject == "L5 InferencePool.endpointPickerRef"
        for v in report.violations
    )


def test_falsify_orphan_cohort(ir: MissionIR, rendered: tuple[str, str, str]) -> None:
    l2, l4, l5 = rendered
    docs = [d for d in yaml.safe_load_all(l4) if d is not None]
    docs.append({
        "apiVersion": "kueue.x-k8s.io/v1beta2",
        "kind": "Cohort",
        "metadata": {"name": "orphan-cohort"},
        "spec": {},
    })

    report = verify(ir, l2=l2, l4=yaml.safe_dump_all(docs), l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "singleton_control_objects" and v.subject == "Cohort"
        for v in report.violations
    )


def test_falsify_clusterqueue_wrong_cohort(
    ir: MissionIR, rendered: tuple[str, str, str]
) -> None:
    l2, l4, l5 = rendered
    docs = [d for d in yaml.safe_load_all(l4) if d is not None]
    for doc in docs:  # rename the one Cohort and repoint the CQ so the ref still resolves
        if doc.get("kind") == "Cohort":
            doc["metadata"]["name"] = "wrong-cohort"
        if doc.get("kind") == "ClusterQueue":
            doc["spec"]["cohortName"] = "wrong-cohort"

    report = verify(ir, l2=l2, l4=yaml.safe_dump_all(docs), l5=l5)

    assert report.ok is False
    assert any(
        v.invariant == "tenant_mission_consistency" and v.subject == "L4 ClusterQueue.cohortName"
        for v in report.violations
    )
