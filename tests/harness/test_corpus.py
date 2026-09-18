"""Unit tests for the E1 seeded contract corpus (deterministic, rule-complete)."""

from __future__ import annotations

from mqi.harness.corpus import generate

_GUARD_RULES = {"R1", "R2", "R3a", "R3b", "R3c", "R4", "unknown-tenant"}


def test_generate_is_deterministic() -> None:
    a = generate(1337, n_valid=12)
    b = generate(1337, n_valid=12)
    assert [c.contract_yaml for c in a] == [c.contract_yaml for c in b]
    assert [c.id for c in a] == [c.id for c in b]


def test_generate_varies_by_seed() -> None:
    a = generate(1, n_valid=12)
    b = generate(2, n_valid=12)
    # the valid contracts are seeded-random, so at least one differs across seeds
    assert [c.contract_yaml for c in a] != [c.contract_yaml for c in b]


def test_corpus_covers_every_guard_rule_exactly_once() -> None:
    cases = generate(7, n_valid=5)
    categories = [c.category for c in cases]
    for rule in _GUARD_RULES:
        assert categories.count(rule) == 1, f"{rule} not present exactly once"
    assert categories.count("valid") == 5


def test_valid_cases_expect_no_rejection_adversarial_do() -> None:
    for c in generate(99, n_valid=8):
        if c.category == "valid":
            assert not c.expect_reject and c.reason_substring == "" and c.expected_stage == "allow"
        else:
            assert c.expect_reject and c.reason_substring != "" and c.expected_stage == "guard"


def test_n_valid_controls_valid_count() -> None:
    assert sum(c.category == "valid" for c in generate(3, n_valid=30)) == 30
    assert len(generate(3, n_valid=30)) == 30 + len(_GUARD_RULES)
