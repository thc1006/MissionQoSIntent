"""Pins the E1 corpus reason-substrings against the REAL OPA guard (needs opa on PATH).

Companion to test_e1.py (fake guards, for speed): every adversarial corpus case runs through the
real policy and must be denied at the GUARD stage with its rule-unique substring present. A reword
of a rego deny-message (which would silently flip `make e1` to a false REJECTED) fails HERE instead.
The suite already depends on opa via tests/ir/test_guard_integration.py.
"""

from __future__ import annotations

from mqi.harness.corpus import generate
from mqi.harness.e1 import evaluate_case
from mqi.policy import evaluate


def test_every_adversarial_substring_matches_the_real_guard() -> None:
    for case in generate(1337, n_valid=1):
        if not case.expect_reject:
            continue
        out = evaluate_case(case, guard=evaluate)  # real OPA guard
        assert out.stage == "guard", (case.category, out.stage, out.reason)
        assert case.reason_substring.lower() in out.reason.lower(), (case.category, out.reason)
