# MissionQoSIntent — Claude Code Guide

Compiler: declarative multi-tenant QoS contracts → policy-guarded **typed IR** → verifiable
**cross-layer** admission/scheduling control plane for GenAI inference on Kubernetes.
Novelty = the compiler / IR / policy-guard + cross-layer verifiable consistency — do NOT restate it in code.

## Build / test / lint (Python 3.12 · uv + hatch)
- `make test` pytest · `make cov` coverage gate (fail-under=90) · `make all` lint+type+cov
- `make lint` ruff · `make type` mypy --strict
- One test: `uv run pytest tests/<file>.py::<test> -q`
- Policy tests: `make policy-test` (`opa test policy -v --coverage --fail-on-empty`)

## Global rules
1. **TDD** — red → green → refactor; write the failing test first wherever code exists.
2. **Small CLs** — one focused concern per commit; keep every diff reviewable.
3. **Boy Scout** — leave touched code cleaner than you found it.
4. **Always verify** — run `make all` before saying "done"; never claim a fact you didn't check.
5. **No AI attribution** — commits/PRs carry none. `.claude/settings.json` `attribution: {commit:"", pr:"", sessionUrl:false}` hides the commit trailer, PR text, and session link; `attribution` supersedes the deprecated `includeCoAuthoredBy`. Never add a `Co-Authored-By` trailer.

## Verified stack (rechecked 2026-06-25 — do NOT bump without re-verifying the ledger)
- Kubernetes **v1.36** · DRA `resource.k8s.io/v1`
- Kueue **v0.18.1** · `kueue.x-k8s.io/v1beta2`
- Gateway API Inference Extension (GAIE) **v1.5.0** · `inference.networking.k8s.io/v1`
- Policy: OPA **v1.18.1** / Rego v1; guard at `policy/` (package `missionqos.guard`)

## Architecture — one contract → 5 consistent layers (docs/architecture/layers-L1-L5.md)
- **L1** inference engine (external): vLLM/Triton — consumes 5 metrics, not rendered
- **L2** request-level admission (built): deferred-red slack gate
- **L3** group throttling (built): GroupTB + Saturation Gate
- **L4** quota & devices (consume): Kueue + DRA
- **L5** gateway (consume): GAIE InferencePool / EndpointPickerConfig
Packages: `contracts` schema · `ir` typed SSOT · `policy` OPA guard · `renderers` L2–L5
· `verifier` cross-layer invariants · `runtime` L2/L3 mechanisms · `harness` eval.

@docs/ — arc42 SDD (`SDD.md`) + the 8 MADR ADRs (`docs/decisions/`).
