---
description: Check the working diff is one small, focused change (full body in a later stage).
---

# /small-cl-check — reviewable-diff guard (STUB, Stage 0)

The full heuristics are specified in a later stage. For now, follow **CLAUDE.md rule 2 (Small CLs)**:

1. Run `git diff --stat` (and `git status`).
2. If the change mixes unrelated concerns or is large, propose how to split it into smaller commits.
