"""Post-deploy E2E assertions against the LIVE kind cluster (run by run.sh ASSERT phase).

Scope (stated honestly — see run.sh header):
  * REAL, exercised end-to-end on a real cluster: L4 (Kueue quota + DRA device allocation) and the
    L2/L3 admission control plane (the real AdmissionStack running in a real pod). Cross-layer
    same-source is checked by comparing LIVE cluster objects to the compiled bundle.
  * STUBBED BY DESIGN: the L1 inference-engine load/saturation signal is a scriptable in-memory
    stub (L1 is an EXTERNAL layer — "consumes 5 metrics, not rendered", per the architecture),
    driven via POST /load,/saturation so ADMIT/DEFER/DROP is exercised deterministically.
  * ARTIFACT-LEVEL ONLY (NOT a running data plane): L5 GAIE. We apply the rendered InferencePool and
    assert it is accepted + schema-valid against the REAL GAIE v1 CRD. We do NOT stand up a gateway
    controller / EPP / model-server / HTTPRoute, so InferencePool Accepted/ResolvedRefs and a
    gateway HTTP 200 are OUT OF SCOPE here (that full data plane is Stage-10 E3). Never claim more.

Uses kubectl over subprocess (no python k8s client dependency); KUBECONFIG + TENANT_NS + MISSION +
BUNDLE_DIR come from the environment set by run.sh. These are real cluster reads/writes.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

NS = os.environ.get("TENANT_NS", "ops-admin")
MISSION = os.environ.get("MISSION", "urban-edge-2026")
BUNDLE_DIR = Path(os.environ["BUNDLE_DIR"]) if os.environ.get("BUNDLE_DIR") else None
REPO_ROOT = Path(__file__).resolve().parents[2]


def kubectl(*args: str, check: bool = True, stdin: str | None = None) -> str:
    proc = subprocess.run(
        ["kubectl", *args], capture_output=True, text=True, input=stdin, timeout=120
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"kubectl {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def kubectl_json(*args: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(kubectl(*args, "-o", "json"))
    return data


def until(predicate: Callable[[], bool], *, attempts: int = 40, sleep_s: float = 2.0) -> bool:
    """Poll `predicate` until True or attempts run out (for cluster state that settles async)."""
    for _ in range(attempts):
        if predicate():
            return True
        time.sleep(sleep_s)
    return False


def _docs(path: Path) -> list[dict[str, Any]]:
    return [d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict)]


def _first(docs: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    return next(d for d in docs if d.get("kind") == kind)


def test_dra_resourceslices_published() -> None:
    slices = kubectl_json("get", "resourceslices")["items"]
    drivers = {s["spec"]["driver"] for s in slices}
    assert "gpu.example.com" in drivers, f"no gpu.example.com ResourceSlices; drivers={drivers}"
    gpu_slices = [s for s in slices if s["spec"]["driver"] == "gpu.example.com"]
    devices = sum(len(s["spec"].get("devices", [])) for s in gpu_slices)
    assert devices >= 1, "gpu.example.com published a ResourceSlice with zero devices"


def test_clusterqueue_and_localqueue_active() -> None:
    cq = kubectl_json("get", "clusterqueue", f"{NS}-cq")
    conds = {c["type"]: c["status"] for c in cq.get("status", {}).get("conditions", [])}
    assert conds.get("Active") == "True", f"ClusterQueue not Active: {conds}"
    lq = kubectl_json("-n", NS, "get", "localqueue", f"{NS}-lq")
    lconds = {c["type"]: c["status"] for c in lq.get("status", {}).get("conditions", [])}
    assert lconds.get("Active") == "True", f"LocalQueue not Active: {lconds}"


def test_gpu_workload_admitted_and_quota_charged_exactly_once() -> None:
    # --wait so a stale Job+Workload from a prior --reuse run is gone before we create the new one.
    kubectl("-n", NS, "delete", "job", "e2e-gpu-consumer", "--ignore-not-found", "--wait=true")
    assert until(
        lambda: not any(
            w["metadata"]["name"].startswith("job-e2e-gpu-consumer")
            for w in kubectl_json("-n", NS, "get", "workloads")["items"]
        ),
        attempts=15,
        sleep_s=2,
    ), "a prior e2e-gpu-consumer Workload did not clear before the new run"

    job = f"""
apiVersion: batch/v1
kind: Job
metadata:
  name: e2e-gpu-consumer
  namespace: {NS}
  labels:
    kueue.x-k8s.io/queue-name: {NS}-lq
    kueue.x-k8s.io/priority-class: mqi-priority-100
spec:
  suspend: true
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      resourceClaims:
      - name: gpu
        resourceClaimTemplateName: gpu-40g-claim
      containers:
      - name: main
        image: registry.k8s.io/e2e-test-images/busybox:1.36.1-1
        command: ["sh", "-c", "sleep 120"]
        resources:
          claims:
          - name: gpu
"""
    kubectl("apply", "-f", "-", stdin=job)

    def _admitted() -> bool:
        for wl in kubectl_json("-n", NS, "get", "workloads")["items"]:
            if wl["metadata"]["name"].startswith("job-e2e-gpu-consumer"):
                conds = {c["type"]: c["status"] for c in wl.get("status", {}).get("conditions", [])}
                if conds.get("Admitted") == "True":
                    return True
        return False

    assert until(_admitted), "Kueue did not admit the DRA GPU workload within timeout"

    def _quota_charged_once() -> bool:
        cq = kubectl_json("get", "clusterqueue", f"{NS}-cq")
        status = cq.get("status", {})
        if status.get("admittedWorkloads") != 1:
            return False
        used = {
            r["name"]: r["total"]
            for fu in status.get("flavorsUsage", [])
            if fu["name"] == "gpu-40g"
            for r in fu["resources"]
        }
        return used.get("gpu-40g") == "1"

    assert until(_quota_charged_once), "gpu-40g quota not charged exactly once (admitted=1, used=1)"

    def _device_allocated() -> bool:
        claims = kubectl_json("-n", NS, "get", "resourceclaims")["items"]
        return any(
            d.get("driver") == "gpu.example.com"
            for c in claims
            for d in c.get("status", {}).get("allocation", {}).get("devices", {}).get("results", [])
        )

    assert until(_device_allocated), "no real gpu.example.com device allocated to the claim"


def test_inferencepool_applied_and_schema_valid_against_real_crd() -> None:
    # SCOPE: artifact-level only. This proves the rendered InferencePool is accepted by the REAL
    # GAIE v1 CRD (the schema fixes were driven by this). It does NOT assert Accepted/ResolvedRefs
    # or any routed traffic — no gateway/EPP/backend is deployed here (that is Stage-10 E3).
    pool = kubectl_json("-n", NS, "get", "inferencepool", f"{MISSION}-pool")
    spec = pool["spec"]
    assert spec["selector"]["matchLabels"]["app"] == f"{MISSION}-inference"
    assert spec["targetPorts"][0]["number"] == 8000
    assert spec["endpointPickerRef"]["name"] == f"{MISSION}-epp"
    assert spec["endpointPickerRef"]["port"]["number"] == 9002


def _metric(text: str, name: str) -> int:
    """Exact value of a Prometheus counter line `name <int>` (not a substring match)."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == name:
            return int(parts[1])
    raise AssertionError(f"metric {name!r} not found in /metrics")


def test_admission_service_admit_defer_drop_live() -> None:
    # Restart the pod first so metrics start at zero and the L2 gate is empty — deterministic and
    # idempotent under --reuse (fixed request ids can't collide with a prior run's in-flight one).
    kubectl("-n", NS, "rollout", "restart", "deploy/mqi-admission")
    kubectl("-n", NS, "rollout", "status", "deploy/mqi-admission", "--timeout=120s")
    drive = r"""
import json, urllib.request as u
def call(m, p, o=None):
    d = json.dumps(o).encode() if o is not None else None
    req = u.Request("http://127.0.0.1:8080" + p, data=d, method=m)
    return u.urlopen(req, timeout=3).read().decode()
def adm(wid, rid):
    return json.loads(call("POST", "/admit", {"workload_id": wid, "request_id": rid}))["admission"]
assert call("GET", "/healthz").strip() == "ok"
call("POST", "/load", {"slots": 1, "min_service_ms": 1})
assert adm("wl-0-emergency-routing", "e1") == "admit"
call("POST", "/load", {"slots": 0, "min_service_ms": 1})
assert adm("wl-1-city-monitoring", "e2") == "defer"
call("POST", "/load", {"slots": 1, "min_service_ms": 100000})
assert adm("wl-0-emergency-routing", "e3") == "drop"
print(call("GET", "/metrics"))
"""
    exec_args = ("-n", NS, "exec", "-i", "deploy/mqi-admission", "--", "python", "-")
    metrics = kubectl(*exec_args, stdin=drive)
    assert _metric(metrics, "mqi_l2_admitted") == 1
    assert _metric(metrics, "mqi_l2_deferred") == 1
    assert _metric(metrics, "mqi_l2_dropped") == 1


def test_live_objects_match_the_compiled_bundle() -> None:
    # Cross-layer same-source, LIVE: the objects the cluster actually holds must match what
    # `mqi compile` produced (the bridge only rewrites the DeviceClass CEL, checked separately).
    assert BUNDLE_DIR is not None and (BUNDLE_DIR / "l4.yaml").exists(), (
        "BUNDLE_DIR/l4.yaml missing — cannot cross-check live objects (hard failure, not skip)"
    )
    l4 = _docs(BUNDLE_DIR / "l4.yaml")
    l5 = _docs(BUNDLE_DIR / "l5.yaml")
    want_cohort = _first(l4, "ClusterQueue")["spec"]["cohortName"]
    want_pool = _first(l5, "InferencePool")

    live_cq = kubectl_json("get", "clusterqueue", f"{NS}-cq")
    assert live_cq["spec"]["cohortName"] == want_cohort, "live ClusterQueue.cohortName != compiled"
    live_pool = kubectl_json("-n", NS, "get", "inferencepool", f"{MISSION}-pool")
    assert live_pool["spec"]["endpointPickerRef"]["name"] == want_pool["spec"]["endpointPickerRef"][
        "name"
    ], "live InferencePool.endpointPickerRef != compiled"
    want_dc = {d["metadata"]["name"] for d in l4 if d.get("kind") == "DeviceClass"}
    live_dc = {d["metadata"]["name"] for d in kubectl_json("get", "deviceclasses")["items"]}
    assert want_dc, "compiled bundle emitted no DeviceClass docs — nothing to cross-check"
    assert want_dc <= live_dc, f"compiled DeviceClasses {want_dc} not all live ({live_dc})"

    # and the compiled bundle itself still verifies (static re-check; NOT skipped)
    proc = subprocess.run(
        ["uv", "run", "mqi", "verify", str(BUNDLE_DIR)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"mqi verify failed on the deployed bundle: {proc.stderr}"
