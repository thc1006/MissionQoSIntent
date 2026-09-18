"""Python client for the OPA/Rego policy guard (invokes `opa eval` as a subprocess)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Repo `policy/` bundle (rego + the data.json entitlement fixture). Relies on the editable install
# so __file__ resolves under src/; override via `policy_dir` when the layout differs.
_DEFAULT_POLICY_DIR = Path(__file__).resolve().parents[3] / "policy"
_QUERY = '{"allow": data.missionqos.guard.allow, "deny": data.missionqos.guard.deny}'


@dataclass(frozen=True)
class GuardDecision:
    """Outcome of evaluating a contract against the policy guard."""

    allowed: bool
    reasons: tuple[str, ...]


class PolicyDenied(Exception):
    """Raised when the policy guard denies a contract; carries the deny reasons."""

    def __init__(self, reasons: Iterable[str]) -> None:
        self.reasons = tuple(reasons)
        super().__init__("policy guard denied: " + "; ".join(self.reasons))


class GuardUnavailable(Exception):
    """Raised when the guard cannot be evaluated (opa missing, bad bundle, malformed output)."""


def evaluate(
    contract_json: dict[str, Any],
    *,
    policy_dir: Path = _DEFAULT_POLICY_DIR,
    opa_bin: str = "opa",
) -> GuardDecision:
    """Evaluate a contract JSON against the Rego guard via `opa eval` and return the decision.

    Raises:
        GuardUnavailable: if opa is missing, the bundle fails to load, or the output is malformed.
    """
    try:
        proc = subprocess.run(
            [opa_bin, "eval", "-d", str(policy_dir), "-I", "--format", "json", _QUERY],
            input=json.dumps(contract_json),
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise GuardUnavailable(f"opa binary not found: {opa_bin!r}") from exc
    except subprocess.CalledProcessError as exc:
        raise GuardUnavailable(f"opa eval failed: {exc.stderr.strip()}") from exc

    try:
        value = json.loads(proc.stdout)["result"][0]["expressions"][0]["value"]
        return GuardDecision(allowed=bool(value["allow"]), reasons=tuple(value["deny"]))
    except (KeyError, IndexError, ValueError) as exc:
        raise GuardUnavailable(f"unexpected opa eval output: {proc.stdout!r}") from exc
