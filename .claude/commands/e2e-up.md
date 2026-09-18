---
description: Stand up the full real-cluster E2E (kind + DRA + Kueue + GAIE + L2/L3 service) and assert cross-layer consistency.
---

# /e2e-up — Stage-9 end-to-end harness

Runs the REAL end-to-end harness in `test/e2e/`: no mocks, a real kind v1.36.1 cluster with real
dra-example-driver (simulated GPUs), Kueue, and GAIE, plus the containerized L2/L3 admission service.

## Steps

1. Run `make e2e` (which shells `test/e2e/run.sh`). Phases: PREFLIGHT → CODE-CHECK → PROVISION →
   DRA → KUEUE → GAIE → BUILD → DEPLOY → ASSERT → TEARDOWN. Teardown always runs on exit (trap);
   pass `E2E_FLAGS=--keep` to leave the cluster up for debugging, or `E2E_FLAGS=--reuse` to reuse one.
2. Requires: `kind`, `kubectl`, `helm`, `podman`, `git`, `uv` on PATH, and network access (pulls
   images + installs Kueue/GAIE from upstream releases). Rootless podman is the kind provider.
3. On success the ASSERT phase (pytest `test/e2e/assert_e2e.py`) has verified, on the LIVE cluster:
   ResourceSlices published; ClusterQueue/LocalQueue Active; a DRA GPU workload admitted with quota
   charged exactly once and a real device bound; the InferencePool applied with the v1 shape; the
   deployed L2/L3 service exhibiting ADMIT/DEFER/DROP with live `/metrics`; and `mqi verify` passing
   on the deployed bundle.
4. Report a PASS/FAIL table with the real `kubectl` evidence. **If any layer was mocked or skipped,
   FAIL it explicitly — never fabricate cluster output.**

Run it, then summarize the phase results and the DoD evidence.
