"""Verify the rendered L2/L4/L5 artifacts against the IR and emit a consistency report."""

from __future__ import annotations

from mqi.ir import MissionIR
from mqi.verifier.bundle import RenderedBundle
from mqi.verifier.invariants import INVARIANTS
from mqi.verifier.models import ConsistencyReport, Violation


def verify(ir: MissionIR, *, l2: str, l4: str, l5: str) -> ConsistencyReport:
    """Prove the rendered artifacts are consistent with the IR (deterministic report)."""
    bundle = RenderedBundle.parse(l2, l4, l5)
    proven: list[str] = []
    violations: list[Violation] = []
    for name, checker in INVARIANTS:
        found = checker(ir, bundle)
        if found:
            violations.extend(found)
        else:
            proven.append(name)
    return ConsistencyReport(ok=not violations, proven=tuple(proven), violations=tuple(violations))
