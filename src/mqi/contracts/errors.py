"""Typed error raised when a contract fails to parse or validate."""

from __future__ import annotations


class ContractError(Exception):
    """A contract rejection with a machine-readable code and a JSON path to the offender.

    Attributes:
        code: stable machine-readable reason (e.g. ``"missing"``, ``"greater_than"``,
            ``"enum"``, ``"extra_forbidden"``, ``"deadline_throughput_conflict"``).
        path: dotted JSON path to the offending field (e.g. ``"spec.workloads[0].slo.deadline"``),
            or ``""`` when the whole document is at fault.
        message: human-readable explanation.
    """

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        location = f" at {path}" if path else ""
        super().__init__(f"[{code}]{location}: {message}")
