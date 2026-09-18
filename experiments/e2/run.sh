#!/usr/bin/env bash
# E2 orchestrator (run on the cluster host, e.g. 4060-dev): compile the E2 contract, start the real
# L2/L3 admission gate (mqi.serve) with the compiled IR, port-forward the real vLLM service, then run
# the load driver (baseline vs gated). Cleans up the gate + port-forward on exit. `make e2`.
set -euo pipefail
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SELF/../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/mqi-e2exp.XXXXXX")"
NS="${MQI_EXP_NS:-mqi-exp}"
GATE_PID=""
PF_PID=""

cleanup() {
  [ -n "$GATE_PID" ] && kill "$GATE_PID" 2>/dev/null || true
  [ -n "$PF_PID" ] && kill "$PF_PID" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

cd "$REPO"
echo "[e2] compiling contract -> ir.json"
uv run mqi compile experiments/e2/contract.yaml -o "$WORK/bundle" >/dev/null

echo "[e2] starting L2/L3 admission gate on 127.0.0.1:8080"
MQI_IR_PATH="$WORK/bundle/ir.json" MQI_LISTEN=127.0.0.1:8080 uv run python -m mqi.serve \
  >"$WORK/gate.log" 2>&1 &
GATE_PID=$!

echo "[e2] port-forwarding vLLM svc/vllm -> 127.0.0.1:18000"
kubectl -n "$NS" port-forward svc/vllm 18000:8000 >"$WORK/pf.log" 2>&1 &
PF_PID=$!

echo "[e2] waiting for gate + vLLM to be ready"
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:8080/healthz >/dev/null 2>&1 && break; sleep 1; done
curl -sf http://127.0.0.1:8080/healthz >/dev/null || { echo "[e2] gate did not come up"; cat "$WORK/gate.log"; exit 1; }
for _ in $(seq 1 90); do curl -sf http://127.0.0.1:18000/health >/dev/null 2>&1 && break; sleep 2; done
curl -sf http://127.0.0.1:18000/health >/dev/null || { echo "[e2] vLLM not reachable"; cat "$WORK/pf.log"; exit 1; }

echo "[e2] running load driver (baseline vs gated)"
uv run python experiments/e2/run.py
