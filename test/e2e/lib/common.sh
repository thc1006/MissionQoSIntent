#!/usr/bin/env bash
# Shared helpers for the Stage-9 E2E harness: logging, retries, and kubectl-wait wrappers.
# Sourced by run.sh and the per-layer install scripts. No side effects on source.

set -euo pipefail

# --- configuration (override via env) ------------------------------------------------------------
export CLUSTER_NAME="${CLUSTER_NAME:-mqi-e2e}"
export KIND_EXPERIMENTAL_PROVIDER="${KIND_EXPERIMENTAL_PROVIDER:-podman}"
export TENANT_NS="${TENANT_NS:-ops-admin}"
export MISSION="${MISSION:-urban-edge-2026}"
export DRIVER_NAME="${DRIVER_NAME:-gpu.example.com}"
export DRA_DRIVER_VERSION="${DRA_DRIVER_VERSION:-v0.3.0}"
export KUEUE_VERSION="${KUEUE_VERSION:-v0.18.1}"
export GAIE_VERSION="${GAIE_VERSION:-v1.5.0}"
export GWAPI_VERSION="${GWAPI_VERSION:-v1.3.0}"
export ADMISSION_IMAGE="${ADMISSION_IMAGE:-localhost/mqi-admission:e2e}"

# repo + scratch paths
E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export E2E_DIR
REPO_ROOT="$(cd "$E2E_DIR/../.." && pwd)"
export REPO_ROOT
export WORK_DIR="${WORK_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/mqi-e2e.XXXXXX")}"
export BUNDLE_DIR="$WORK_DIR/bundle"
export BRIDGED_DIR="$WORK_DIR/bridged"

# --- logging -------------------------------------------------------------------------------------
_ts() { date -u +%H:%M:%S 2>/dev/null || echo "--:--:--"; }
log()  { printf '\033[1;34m[%s] ==> %s\033[0m\n' "$(_ts)" "$*" >&2; }
ok()   { printf '\033[1;32m[%s] OK  %s\033[0m\n' "$(_ts)" "$*" >&2; }
warn() { printf '\033[1;33m[%s] !!  %s\033[0m\n' "$(_ts)" "$*" >&2; }
die()  { printf '\033[1;31m[%s] XX  %s\033[0m\n' "$(_ts)" "$*" >&2; exit 1; }

# --- prerequisites -------------------------------------------------------------------------------
require_tools() {
  local missing=()
  for t in "$@"; do command -v "$t" >/dev/null 2>&1 || missing+=("$t"); done
  [ ${#missing[@]} -eq 0 ] || die "missing required tools: ${missing[*]}"
}

# kubeconfig for the harness cluster (exported so kubectl/helm use it)
use_kubeconfig() {
  export KUBECONFIG="$WORK_DIR/kubeconfig"
  kind get kubeconfig --name "$CLUSTER_NAME" > "$KUBECONFIG" 2>/dev/null \
    || die "cluster $CLUSTER_NAME not found; run provision first"
}

# retry <attempts> <sleep-seconds> <cmd...> — run cmd until it succeeds or attempts run out.
retry() {
  local attempts="$1" sleep_s="$2"; shift 2
  local i=1
  until "$@"; do
    [ "$i" -ge "$attempts" ] && return 1
    i=$((i + 1)); sleep "$sleep_s"
  done
}

# kubectl helper bound to the harness kubeconfig
k() { kubectl "$@"; }
