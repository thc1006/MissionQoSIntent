---
description: Drive one Red-Green-Refactor cycle for a single behavior
argument-hint: [behavior to implement]
allowed-tools: Read, Edit, Bash(pytest*), Bash(ruff*), Bash(mypy*)
---
Implement ONE behavior via strict TDD: $ARGUMENTS
1. RED: write the smallest failing test that specifies this behavior; run pytest and show
   it fails for the RIGHT reason (missing behavior, not a typo).
2. GREEN: write the minimal code to pass — obvious implementation or fake-it; run pytest, show green.
3. REFACTOR: remove duplication and improve names WITHOUT changing behavior; keep tests green.
Do NOT implement more than this one behavior. If you discover new cases, append them to a
test list in the test file's docstring, don't build them now. End by showing the diff.