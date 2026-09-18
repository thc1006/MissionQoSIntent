---
description: Verify a stage's deliverables are complete and green (full body in a later stage).
---

# /verify-stage — stage completion gate (STUB, Stage 0)

The per-stage checklist is specified in a later stage. For now:

1. Run `make all` (lint + type + cov) and confirm it is green.
2. Confirm the stage's declared deliverables exist and match the SDD (`@docs/`).
3. Report a PASS/FAIL table. **Do not fix anything in the verify pass** — only report.
