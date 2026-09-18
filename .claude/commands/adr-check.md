---
description: Check code/decisions against the MADR ADRs in docs/decisions/ (full body later).
---

# /adr-check — decision-conformance check (STUB, Stage 0)

The full body is specified in a later stage. For now:

1. Cross-check the change against `docs/decisions/` — especially ADR-0002 (typed IR as SSOT),
   ADR-0003 (policy guard), and ADR-0004 (deferred-red scope vs GAIE).
2. Flag any drift from an accepted decision; if a decision is actually changing, open a new ADR
   from `docs/decisions/adr-template.md` rather than silently diverging.
