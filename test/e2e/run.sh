#!/usr/bin/env bash
# Stage-9 END-TO-END harness: compile a real contract, stand up a REAL kind cluster with REAL
# DRA (dra-example-driver) + Kueue + GAIE, deploy the containerized L2/L3 admission service, apply
# the bridged L4/L5 artifacts, and assert cross-layer consistency on the live cluster.
#
# SCOPE (honest — see assert_e2e.py for the per-check detail):
#   * REAL, exercised on the cluster: L4 (Kueue quota + DRA device allocation) and the L2/L3
#     admission control plane (the real AdmissionStack in a real pod); live objects are cross-checked
#     against the compiled bundle (same-source, live).
#   * STUBBED BY DESIGN: the external L1 inference-engine load/saturation signal, driven via
#     /load,/saturation to exercise ADMIT/DEFER/DROP deterministically. L1 is out of scope.
#   * ARTIFACT-LEVEL ONLY: L5 GAIE — the rendered InferencePool is applied + schema-validated against
#     the real GAIE v1 CRD. A full gateway data plane (controller/EPP/backend/HTTPRoute/HTTP 200) is
#     NOT stood up here; that is Stage-10 E3. The harness does not claim otherwise.
#
# Phases: PREFLIGHT -> CODE-CHECK -> PROVISION -> DRA -> KUEUE -> GAIE -> BUILD -> PRE-DEPLOY ->
#         DEPLOY -> ASSERT -> TEARDOWN. Idempotent (safe to re-run) and headless (claude -p / CI).
# Teardown runs on exit via trap unless --keep (or --reuse) is given; any phase failing aborts
# non-zero (and tears down too, unless --keep/--reuse asked to preserve the cluster for debugging).
#
# Usage: test/e2e/run.sh [--keep] [--no-teardown] [--reuse]
#   --keep / --no-teardown  leave the cluster running after the run (for debugging)
#   --reuse                 reuse an existing cluster instead of recreating it (implies --keep, so
#                           the cluster survives for the next --reuse invocation)
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=test/e2e/lib/common.sh
source "$SELF_DIR/lib/common.sh"

KEEP=0
REUSE=0
for arg in "$@"; do
  case "$arg" in
    --keep|--no-teardown) KEEP=1 ;;
    --reuse) REUSE=1; KEEP=1 ;;  # reuse implies keep, else teardown deletes what the next run reuses
    *) die "unknown flag: $arg" ;;
  esac
done

teardown() {
  local code=$?
  if [ "$KEEP" -eq 1 ]; then
    warn "leaving cluster '$CLUSTER_NAME' up (--keep); delete with: kind delete cluster --name $CLUSTER_NAME"
  else
    log "TEARDOWN: deleting cluster '$CLUSTER_NAME'"
    kind delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
  fi
  [ -n "${WORK_DIR:-}" ] && rm -rf "$WORK_DIR" 2>/dev/null || true
  [ "$code" -eq 0 ] && ok "E2E COMPLETE (exit 0)" || die_noexit "E2E FAILED (exit $code)"
  exit "$code"
}
die_noexit() { printf '\033[1;31m[%s] XX  %s\033[0m\n' "$(_ts)" "$*" >&2; }
trap teardown EXIT

# ---------------------------------------------------------------------------------------------------
preflight() {
  log "PREFLIGHT: checking tools"
  require_tools kind kubectl helm podman git uv
  ok "tools present; WORK_DIR=$WORK_DIR"
}

codecheck() {
  log "CODE-CHECK (pre-deploy): compiler gate + harness lint/type + bridge unit tests"
  ( cd "$REPO_ROOT" && make all ) || die "CODE-CHECK: 'make all' failed (compiler/service gate)"
  ( cd "$REPO_ROOT" && uv run ruff check test/e2e ) || die "CODE-CHECK: ruff on test/e2e failed"
  ( cd "$REPO_ROOT" && uv run mypy --strict test/e2e/assert_e2e.py test/e2e/bridge.py ) \
    || die "CODE-CHECK: mypy on test/e2e failed"
  ( cd "$REPO_ROOT" && uv run pytest test/e2e/test_bridge.py -q ) \
    || die "CODE-CHECK: bridge unit tests failed"
  ok "CODE-CHECK: green (make all + harness lint/type + bridge tests)"
}

provision() {
  if [ "$REUSE" -eq 1 ] && kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
    log "PROVISION: reusing existing cluster '$CLUSTER_NAME'"
  else
    log "PROVISION: creating kind cluster '$CLUSTER_NAME' (kindest/node v1.36.1, 3 nodes)"
    kind delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
    kind create cluster --name "$CLUSTER_NAME" --config "$E2E_DIR/kind-dra.yaml" --wait 120s
  fi
  use_kubeconfig
  k api-resources --api-group=resource.k8s.io 2>/dev/null | grep -q deviceclasses \
    || die "resource.k8s.io/v1 (DRA) not served by the cluster"
  ok "PROVISION: cluster up, DRA API (resource.k8s.io/v1) served"
}

install_dra() {
  log "DRA: installing dra-example-driver $DRA_DRIVER_VERSION (simulated GPUs)"
  local chart="$WORK_DIR/dra-example-driver"
  [ -d "$chart" ] || git clone --depth 1 --branch "$DRA_DRIVER_VERSION" \
    https://github.com/kubernetes-sigs/dra-example-driver.git "$chart" >/dev/null 2>&1
  helm upgrade -i --create-namespace -n dra-example-driver dra-example-driver \
    "$chart/deployments/helm/dra-example-driver" --set image.pullPolicy=IfNotPresent \
    --wait --timeout 180s >/dev/null
  retry 30 3 bash -c "kubectl get resourceslices -o name 2>/dev/null | grep -q ." \
    || die "DRA: no ResourceSlices published by the driver"
  local n; n=$(k get resourceslices -o name | wc -l | tr -d ' ')
  ok "DRA: driver ready, $n ResourceSlice(s) published under $DRIVER_NAME"
}

install_kueue() {
  log "KUEUE: installing $KUEUE_VERSION + DRA integration config"
  k apply --server-side -f \
    "https://github.com/kubernetes-sigs/kueue/releases/download/$KUEUE_VERSION/manifests.yaml" >/dev/null
  k -n kueue-system wait --for=condition=Available deploy/kueue-controller-manager --timeout=180s
  local cfg="$WORK_DIR/kueue-config.yaml"
  k -n kueue-system get cm kueue-manager-config \
    -o jsonpath='{.data.controller_manager_config\.yaml}' > "$cfg"
  if ! grep -q "KueueDRAIntegration" "$cfg"; then  # idempotent: don't append twice on --reuse
    cat >> "$cfg" <<EOF
featureGates:
  KueueDRAIntegration: true
resources:
  deviceClassMappings:
  - name: gpu-24g
    deviceClassNames:
    - gpu-24g
  - name: gpu-40g
    deviceClassNames:
    - gpu-40g
EOF
  fi
  k -n kueue-system create configmap kueue-manager-config \
    --from-file=controller_manager_config.yaml="$cfg" --dry-run=client -o yaml | k apply -f - >/dev/null
  k -n kueue-system rollout restart deploy/kueue-controller-manager >/dev/null
  k -n kueue-system rollout status deploy/kueue-controller-manager --timeout=150s
  # Grep the running pod's startup log; retry because the terminating old pod (gate off, from before
  # the config patch) can transiently be the one `logs deploy/...` selects right after rollout.
  retry 20 3 bash -c 'kubectl -n kueue-system logs deploy/kueue-controller-manager 2>/dev/null \
    | grep -q "\"KueueDRAIntegration\":true"' \
    || die "KUEUE: DRA integration gate not active in controller logs"
  ok "KUEUE: controller up, KueueDRAIntegration enabled, deviceClassMappings applied"
}

install_gaie() {
  log "GAIE: installing Gateway API $GWAPI_VERSION + GAIE $GAIE_VERSION CRDs"
  k apply -f \
    "https://github.com/kubernetes-sigs/gateway-api/releases/download/$GWAPI_VERSION/standard-install.yaml" >/dev/null
  k apply -f \
    "https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/$GAIE_VERSION/manifests.yaml" >/dev/null
  retry 20 2 bash -c "kubectl get crd inferencepools.inference.networking.k8s.io >/dev/null 2>&1" \
    || die "GAIE: InferencePool CRD not established"
  ok "GAIE: CRDs installed (InferencePool inference.networking.k8s.io/v1)"
}

compile_and_bridge() {
  log "BUILD: compiling $MISSION contract + bridging L4 for the cluster"
  rm -rf "$BUNDLE_DIR" "$BRIDGED_DIR"
  (cd "$REPO_ROOT" && uv run mqi compile test/e2e/contract.yaml -o "$BUNDLE_DIR" >/dev/null)
  (cd "$REPO_ROOT" && uv run mqi verify "$BUNDLE_DIR" >/dev/null) || die "BUILD: mqi verify failed"
  (cd "$REPO_ROOT" && uv run python test/e2e/bridge.py "$BUNDLE_DIR" "$BRIDGED_DIR" >/dev/null)
  ok "BUILD: bundle compiled + verified, L4 bridged to $DRIVER_NAME"
}

predeploy_check() {
  log "PRE-DEPLOY: server dry-run of the bridged L4 + rendered InferencePool"
  k create namespace "$TENANT_NS" --dry-run=client -o yaml | k apply -f - >/dev/null
  k apply --server-side --dry-run=server -f "$BRIDGED_DIR/l4.yaml" >/dev/null \
    || die "PRE-DEPLOY: bridged L4 failed server dry-run"
  awk 'BEGIN{RS="---\n"} /kind: InferencePool/{print "---"; print}' "$BUNDLE_DIR/l5.yaml" \
    > "$WORK_DIR/inferencepool.yaml"
  k -n "$TENANT_NS" apply --dry-run=server -f "$WORK_DIR/inferencepool.yaml" >/dev/null \
    || die "PRE-DEPLOY: rendered InferencePool failed server dry-run"
  ok "PRE-DEPLOY: rendered artifacts pass server-side validation"
}

build_and_load_image() {
  log "BUILD: admission service image + kind load"
  (cd "$REPO_ROOT" && podman build -q -f test/e2e/service.Dockerfile -t "$ADMISSION_IMAGE" . >/dev/null)
  podman save "$ADMISSION_IMAGE" -o "$WORK_DIR/admission.tar" >/dev/null 2>&1
  kind load image-archive "$WORK_DIR/admission.tar" --name "$CLUSTER_NAME" >/dev/null 2>&1
  ok "BUILD: image $ADMISSION_IMAGE loaded into the cluster"
}

deploy() {
  log "DEPLOY: applying bridged L4 + InferencePool + L2/L3 service"
  k apply --server-side -f "$BRIDGED_DIR/l4.yaml" >/dev/null
  k -n "$TENANT_NS" apply -f "$WORK_DIR/inferencepool.yaml" >/dev/null
  k -n "$TENANT_NS" create configmap mqi-ir --from-file=ir.json="$BUNDLE_DIR/ir.json" \
    --dry-run=client -o yaml | k apply -f - >/dev/null
  k apply -f "$E2E_DIR/service-deploy.yaml" >/dev/null
  k -n "$TENANT_NS" rollout status deploy/mqi-admission --timeout=120s
  k wait --for=condition=Active clusterqueue/"$TENANT_NS"-cq --timeout=60s >/dev/null 2>&1 || true
  ok "DEPLOY: L4 + InferencePool applied, L2/L3 service running"
}

assertions() {
  log "ASSERT: running post-deploy checks (pytest, live cluster)"
  ( cd "$REPO_ROOT" && KUBECONFIG="$KUBECONFIG" TENANT_NS="$TENANT_NS" MISSION="$MISSION" \
      BUNDLE_DIR="$BUNDLE_DIR" uv run pytest test/e2e/assert_e2e.py -v ) \
    || die "ASSERT: post-deploy assertions failed"
  ok "ASSERT: all post-deploy assertions passed"
}

main() {
  preflight
  codecheck
  provision
  install_dra
  install_kueue
  install_gaie
  compile_and_bridge
  predeploy_check
  build_and_load_image
  deploy
  assertions
}
main "$@"
