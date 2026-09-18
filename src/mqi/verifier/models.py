"""Machine-readable consistency report models (frozen -> deterministic equality + model_dump)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(frozen=True)


class Violation(BaseModel):
    """A single cross-layer inconsistency with a concrete counterexample."""

    model_config = _FROZEN

    invariant: str
    subject: str
    expected: str
    actual: str
    detail: str


class ConsistencyReport(BaseModel):
    """Outcome of verifying the rendered artifacts against the IR."""

    model_config = _FROZEN

    ok: bool
    proven: tuple[str, ...]
    violations: tuple[Violation, ...]
