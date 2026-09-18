"""Experiment E1: consistency + policy-guard evaluation over the seeded contract corpus.

Two arms, both against the REAL compiler:
  * guard arm — compile each `ContractCase`. A valid case must compile + guard-allow + verify
    consistent; an adversarial case must be rejected AT ITS EXPECTED STAGE (all corpus adversarials
    are guard rules, so the OPA GUARD — not the parser — must reject each) with a reason fragment
    UNIQUE to that rule. `false_allow` (an adversarial that slipped through) MUST be 0.
  * injection arm — take the valid contracts, compile them, then mutate exactly ONE rendered layer
    and re-run the cross-layer verifier. There is one injector PER verifier invariant, and each
    checks that ITS target invariant fires — so E1 proves every invariant is live (deleting any one
    makes its injection uncaught) and no injector passes vacuously.

Acceptance is non-vacuous: it requires a non-empty valid set, adversarial set, and injection set,
that every adversarial is caught by the guard, and that the injectors cover every invariant.
The guard is injectable so unit tests run without OPA; `experiments/e1` injects the real `evaluate`.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import yaml

from mqi.contracts import ContractError
from mqi.harness.corpus import ContractCase
from mqi.ir import GuardFn
from mqi.pipeline import compile_contract
from mqi.policy import GuardUnavailable, PolicyDenied, evaluate
from mqi.verifier import verify
from mqi.verifier.invariants import INVARIANTS

_ALL_INVARIANTS = frozenset(name for name, _ in INVARIANTS)


@dataclass(frozen=True)
class CaseOutcome:
    """The observed verdict for one contract case, and whether it matches the case's label."""

    id: str
    category: str
    expect_reject: bool
    rejected: bool
    stage: str  # "allow" | "parse" | "guard" | "guard-unavailable"
    reason: str
    consistent: bool | None  # verify report.ok when allowed; None when rejected
    passed: bool


@dataclass(frozen=True)
class InjectionOutcome:
    """One one-layer mutation of a valid bundle: whether verify caught it, and via its target."""

    contract_id: str
    injector: str
    target_invariant: str
    caught: bool
    target_fired: bool  # the injector's target invariant appears among the violations


def evaluate_case(case: ContractCase, *, guard: GuardFn = evaluate) -> CaseOutcome:
    """Compile one case and classify the outcome against its expected label + stage."""
    rejected, stage, reason, consistent = False, "allow", "", None
    try:
        result = compile_contract(case.contract_yaml, guard=guard)
        consistent = result.report.ok
    except ContractError as exc:
        rejected, stage, reason = True, "parse", exc.message
    except PolicyDenied as exc:
        rejected, stage, reason = True, "guard", "; ".join(exc.reasons)
    except GuardUnavailable as exc:
        rejected, stage, reason = True, "guard-unavailable", str(exc)

    if case.expect_reject:
        # Must be rejected AT the expected stage (guard) with the rule-specific reason — a parse
        # rejection or a coincidental substring from another rule does NOT count as detection.
        passed = (
            rejected
            and stage == case.expected_stage
            and case.reason_substring.lower() in reason.lower()
        )
    else:
        passed = (not rejected) and consistent is True
    return CaseOutcome(
        case.id, case.category, case.expect_reject, rejected, stage, reason, consistent, passed
    )


def _load(text: str) -> dict[str, Any]:
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    return doc


def _docs(text: str) -> list[dict[str, Any]]:
    return [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]


def _mut_l2_tenant(l2: str) -> str:
    d = _load(l2)
    d["metadata"]["tenant"] = "evil-tenant"
    return yaml.safe_dump(d, sort_keys=False)


def _mut_l2_slack(l2: str) -> str:
    d = _load(l2)
    d["spec"]["gates"][0]["slackBasisMs"] = 1  # diverges from the deadline-derived slack
    return yaml.safe_dump(d, sort_keys=False)


def _mut_l2_ondrop(l2: str) -> str:
    d = _load(l2)
    d["spec"]["gates"][0]["onDrop"] = "wrong-fallback"  # != the workload's fallback
    return yaml.safe_dump(d, sort_keys=False)


def _mut_l2_spurious_gate(l2: str) -> str:
    d = _load(l2)
    ghost = copy.deepcopy(d["spec"]["gates"][0])
    ghost["workload"] = "ghost-workload"  # references a workload not in the IR
    d["spec"]["gates"].append(ghost)
    return yaml.safe_dump(d, sort_keys=False)


def _mut_l4_cohort(l4: str) -> str:
    docs = _docs(l4)
    for d in docs:
        if d.get("kind") == "ClusterQueue":
            d["spec"]["cohortName"] = "dangling-cohort"  # resolves to no Cohort object
    return yaml.safe_dump_all(docs, sort_keys=False)


def _mut_l4_device(l4: str) -> str:
    docs = _docs(l4)
    for d in docs:
        if d.get("kind") == "ResourceClaimTemplate":
            d["spec"]["spec"]["devices"]["requests"][0]["exactly"]["deviceClassName"] = "gpu-evil"
    return yaml.safe_dump_all(docs, sort_keys=False)


def _mut_l4_quota(l4: str) -> str:
    docs = _docs(l4)
    for d in docs:
        if d.get("kind") == "ClusterQueue":
            for group in d["spec"]["resourceGroups"]:
                for flavor in group["flavors"]:
                    for resource in flavor["resources"]:
                        resource["nominalQuota"] = 0  # below the workload demand
    return yaml.safe_dump_all(docs, sort_keys=False)


def _mut_l4_extra_cluster_queue(l4: str) -> str:
    docs = _docs(l4)
    extra = copy.deepcopy(next(d for d in docs if d.get("kind") == "ClusterQueue"))
    extra["metadata"]["name"] = "second-cq"  # a second ClusterQueue breaks the singleton invariant
    docs.append(extra)
    return yaml.safe_dump_all(docs, sort_keys=False)


def _mut_l4_duplicate_flavor(l4: str) -> str:
    docs = _docs(l4)
    dup = copy.deepcopy(next(d for d in docs if d.get("kind") == "ResourceFlavor"))
    docs.append(dup)  # two ResourceFlavors with the same name
    return yaml.safe_dump_all(docs, sort_keys=False)


def _mut_l5_priority(l5: str) -> str:
    docs = _docs(l5)
    for d in docs:
        if d.get("kind") == "EndpointPickerConfig":
            d["flowControl"]["priorityBands"][0]["priority"] = 999  # no IR workload has this
    return yaml.safe_dump_all(docs, sort_keys=False)


def _mut_l5_ordering(l5: str) -> str:
    docs = _docs(l5)
    for d in docs:
        if d.get("kind") == "EndpointPickerConfig":
            d["flowControl"]["priorityBands"][0]["orderingPolicyRef"] = "fcfs-ordering-policy"
    return yaml.safe_dump_all(docs, sort_keys=False)


@dataclass(frozen=True)
class Injector:
    """A one-layer mutation and the verifier invariant it is designed to trip."""

    name: str
    layer: str  # "l2" | "l4" | "l5"
    mutate: Callable[[str], str]
    target_invariant: str


# One injector per verifier invariant (checked exhaustive in summarize via `invariants_covered`).
INJECTORS: tuple[Injector, ...] = (
    Injector("l2-tenant", "l2", _mut_l2_tenant, "tenant_mission_consistency"),
    Injector("l2-slack", "l2", _mut_l2_slack, "deadline_slack_alignment"),
    Injector("l2-ondrop", "l2", _mut_l2_ondrop, "fallback_ondrop_alignment"),
    Injector("l2-spurious-gate", "l2", _mut_l2_spurious_gate, "no_spurious_l2_gates"),
    Injector("l4-cohort", "l4", _mut_l4_cohort, "intra_bundle_references_resolve"),
    Injector("l4-device-class", "l4", _mut_l4_device, "l4_device_references_resolve"),
    Injector("l4-quota", "l4", _mut_l4_quota, "device_class_quota_coverage"),
    Injector("l4-extra-cq", "l4", _mut_l4_extra_cluster_queue, "singleton_control_objects"),
    Injector("l4-duplicate-flavor", "l4", _mut_l4_duplicate_flavor, "no_duplicate_named_objects"),
    Injector("l5-priority", "l5", _mut_l5_priority, "priority_band_bijection"),
    Injector("l5-ordering", "l5", _mut_l5_ordering, "deadline_aware_ordering"),
)


def run_injections(valid_yamls: list[str], *, guard: GuardFn = evaluate) -> list[InjectionOutcome]:
    """Compile each valid contract, then verify a one-layer mutation of it (must be caught by its
    target invariant)."""
    outcomes: list[InjectionOutcome] = []
    for i, contract_yaml in enumerate(valid_yamls):
        try:
            result = compile_contract(contract_yaml, guard=guard)
        except (ContractError, PolicyDenied, GuardUnavailable):
            continue  # a 'valid' contract that won't compile is already a false_deny (guard arm)
        layers = {"l2": result.l2, "l4": result.l4, "l5": result.l5}
        for inj in INJECTORS:
            mutated = dict(layers)
            mutated[inj.layer] = inj.mutate(layers[inj.layer])
            report = verify(result.ir, l2=mutated["l2"], l4=mutated["l4"], l5=mutated["l5"])
            fired = {v.invariant for v in report.violations}
            outcomes.append(InjectionOutcome(
                f"valid-{i}", inj.name, inj.target_invariant,
                caught=not report.ok, target_fired=inj.target_invariant in fired,
            ))
    return outcomes


@dataclass(frozen=True)
class E1Summary:
    """Aggregate E1 metrics + the pass/fail acceptance verdict (SDD §10.2)."""

    total_cases: int
    valid_cases: int
    adversarial_cases: int
    false_allow: int  # adversarial contract NOT rejected — MUST be 0
    false_deny: int  # valid contract wrongly rejected — MUST be 0
    guard_detected: int
    parse_detected: int
    all_valid_consistent: bool
    injections: int
    injections_caught: int
    injections_target_fired: int
    invariants_covered: int
    invariants_total: int
    accepted: bool


def summarize(cases: list[CaseOutcome], injections: list[InjectionOutcome]) -> E1Summary:
    """Fold per-case + per-injection outcomes into a NON-VACUOUS E1 acceptance summary."""
    valid = [c for c in cases if not c.expect_reject]
    adversarial = [c for c in cases if c.expect_reject]
    false_allow = sum(1 for c in adversarial if not c.rejected)
    false_deny = sum(1 for c in valid if c.rejected)
    guard_detected = sum(1 for c in adversarial if c.stage == "guard")
    all_valid_consistent = bool(valid) and all(c.consistent for c in valid)
    caught = sum(1 for i in injections if i.caught)
    target_fired = sum(1 for i in injections if i.target_fired)
    covered = {i.target_invariant for i in injections}
    accepted = (
        len(valid) > 0
        and len(adversarial) > 0
        and len(injections) > 0
        and false_allow == 0
        and false_deny == 0
        and guard_detected == len(adversarial)  # every adversarial caught BY THE GUARD
        and all_valid_consistent
        and caught == len(injections)
        and target_fired == len(injections)  # each injection tripped ITS target invariant
        and covered == _ALL_INVARIANTS  # injectors exercise every verifier invariant
        and all(c.passed for c in cases)
    )
    return E1Summary(
        total_cases=len(cases),
        valid_cases=len(valid),
        adversarial_cases=len(adversarial),
        false_allow=false_allow,
        false_deny=false_deny,
        guard_detected=guard_detected,
        parse_detected=sum(1 for c in adversarial if c.stage == "parse"),
        all_valid_consistent=all_valid_consistent,
        injections=len(injections),
        injections_caught=caught,
        injections_target_fired=target_fired,
        invariants_covered=len(covered),
        invariants_total=len(_ALL_INVARIANTS),
        accepted=accepted,
    )
