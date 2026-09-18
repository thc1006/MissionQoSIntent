"""Unit tests for the E1 experiment logic (fake guards; real compile/verify).

Includes regression tests for the soundness holes the E1 review found: a vacuous empty run, an
adversarial caught at parse (not guard), and an injection whose target invariant did not fire.
"""

from __future__ import annotations

from typing import Any

from mqi.harness.corpus import ContractCase, generate
from mqi.harness.e1 import (
    INJECTORS,
    CaseOutcome,
    InjectionOutcome,
    evaluate_case,
    run_injections,
    summarize,
)
from mqi.policy import GuardDecision, GuardUnavailable

_VALID_YAML = generate(0, n_valid=1)[0].contract_yaml


def _allow(_c: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=True, reasons=())


def _deny(_c: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=False, reasons=("denied for test",))


def _unavailable(_c: dict[str, Any]) -> GuardDecision:
    raise GuardUnavailable("opa missing (test)")


def _case(**kw: Any) -> ContractCase:
    base: dict[str, Any] = {
        "id": "t", "category": "valid", "contract_yaml": _VALID_YAML,
        "expect_reject": False, "reason_substring": "", "expected_stage": "allow",
    }
    base.update(kw)
    return ContractCase(**base)


def _clean_cases() -> list[CaseOutcome]:
    cases = [CaseOutcome("v0", "valid", False, False, "allow", "", True, True)]
    for cat in ("R1", "R2", "R3a", "R3b", "R3c", "R4", "unknown-tenant"):
        cases.append(CaseOutcome(cat, cat, True, True, "guard", "reason", None, True))
    return cases


def _clean_injections() -> list[InjectionOutcome]:
    return [InjectionOutcome("valid-0", i.name, i.target_invariant, True, True) for i in INJECTORS]


def test_evaluate_valid_case_allows_and_is_consistent() -> None:
    out = evaluate_case(_case(), guard=_allow)
    assert out.stage == "allow" and not out.rejected and out.consistent is True and out.passed


def test_evaluate_guard_denial_at_guard_stage_passes() -> None:
    case = _case(category="R1", expect_reject=True, reason_substring="denied",
                 expected_stage="guard")
    out = evaluate_case(case, guard=_deny)
    assert out.rejected and out.stage == "guard" and out.passed


def test_evaluate_adversarial_caught_at_parse_does_not_pass() -> None:
    # a guard-rule case rejected by the parser instead of the guard must NOT count as detected
    case = _case(category="R1", contract_yaml="{}\n", expect_reject=True,
                 reason_substring="", expected_stage="guard")
    out = evaluate_case(case, guard=_allow)
    assert out.stage == "parse" and not out.passed


def test_guard_unavailable_does_not_count_as_detection() -> None:
    case = _case(category="R1", expect_reject=True, reason_substring="denied",
                 expected_stage="guard")
    out = evaluate_case(case, guard=_unavailable)
    assert out.stage == "guard-unavailable" and not out.passed


def test_every_injector_hits_its_target_invariant() -> None:
    outcomes = run_injections([_VALID_YAML], guard=_allow)
    assert len(outcomes) == len(INJECTORS)
    failed = [o for o in outcomes if not (o.caught and o.target_fired)]
    assert not failed, failed
    assert {o.target_invariant for o in outcomes} == {i.target_invariant for i in INJECTORS}


def test_run_injections_skips_uncompilable_contracts() -> None:
    # a 'valid'-labelled contract the guard denies must be SKIPPED, not crash the run (it is already
    # recorded as a false_deny by the guard arm). Regression for the missing try/except.
    assert run_injections([_VALID_YAML], guard=_deny) == []


def test_summarize_accepts_a_clean_run() -> None:
    s = summarize(_clean_cases(), _clean_injections())
    assert s.accepted
    assert s.guard_detected == 7 and s.false_allow == 0
    assert s.invariants_covered == s.invariants_total == 11
    assert s.injections_target_fired == len(INJECTORS)


def test_summarize_rejects_vacuous_empty_run() -> None:
    # n_valid=0 (no valid cases, no injections) must NOT be accepted — the review's vacuous hole
    only_adversarial = [c for c in _clean_cases() if c.expect_reject]
    s = summarize(only_adversarial, [])
    assert not s.accepted and s.valid_cases == 0 and s.injections == 0


def test_summarize_rejects_when_adversarial_caught_at_parse() -> None:
    cases = _clean_cases()
    cases[1] = CaseOutcome("R1", "R1", True, True, "parse", "x", None, False)  # guard didn't catch
    s = summarize(cases, _clean_injections())
    assert s.guard_detected == 6 and not s.accepted


def test_summarize_rejects_on_false_allow() -> None:
    cases = [CaseOutcome("r1", "R1", True, False, "allow", "", True, False)]  # adversarial slipped
    s = summarize(cases + [c for c in _clean_cases() if not c.expect_reject], _clean_injections())
    assert s.false_allow == 1 and not s.accepted


def test_summarize_rejects_on_untriggered_target_invariant() -> None:
    injections = _clean_injections()[:-1]
    injections.append(InjectionOutcome("valid-0", "l5-ordering", "deadline_aware_ordering",
                                       caught=True, target_fired=False))  # caught but wrong reason
    s = summarize(_clean_cases(), injections)
    assert s.injections_target_fired < s.injections and not s.accepted
