"""E1 runner: the REAL OPA guard over the seeded corpus -> CSV + results.json + plot.

Invoked by `make e1`. Exit 0 iff the run is ACCEPTED (SDD §10.2: no false-allow, no false-deny, all
valid bundles verify consistent, every injected one-layer inconsistency caught). Not part of the
unit suite — the reusable logic lives in `mqi.harness` (tested there); this is orchestration + I/O.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend; must precede the pyplot import
import matplotlib.pyplot as plt
import yaml

from mqi.harness.corpus import generate
from mqi.harness.e1 import E1Summary, evaluate_case, run_injections, summarize


def _plot(summary: E1Summary, path: Path) -> None:
    labels = ["valid\nconsistent", "guard\ndetected", "injections\ntarget-fired",
              "invariants\ncovered", "false\nallow", "false\ndeny"]
    values = [
        summary.valid_cases if summary.all_valid_consistent else 0,
        summary.guard_detected, summary.injections_target_fired,
        summary.invariants_covered, summary.false_allow, summary.false_deny,
    ]
    colors = ["#2ca02c"] * 4 + ["#d62728"] * 2  # green = good, red = must-be-zero
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(labels, values, color=colors)
    ax.set_ylabel("count")
    ax.set_title(f"E1 consistency + policy-guard  (accepted={summary.accepted})")
    for i, v in enumerate(values):
        ax.text(i, v, str(v), ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    config_path = Path(args[0]) if args else Path(__file__).parent / "config.yaml"
    cfg = yaml.safe_load(config_path.read_text())
    out = Path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)

    cases = generate(cfg["seed"], n_valid=cfg["n_valid"])
    case_outcomes = [evaluate_case(c) for c in cases]  # real guard (mqi.policy.evaluate)
    valid_yamls = [c.contract_yaml for c in cases if c.category == "valid"]
    injections = run_injections(valid_yamls)
    summary = summarize(case_outcomes, injections)

    with (out / "e1_cases.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "expect_reject", "rejected", "stage", "passed", "reason"])
        for o in case_outcomes:
            w.writerow([o.id, o.category, o.expect_reject, o.rejected, o.stage, o.passed, o.reason])
    with (out / "e1_injections.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["contract_id", "injector", "target_invariant", "caught", "target_fired"])
        for inj in injections:
            w.writerow([inj.contract_id, inj.injector, inj.target_invariant,
                        inj.caught, inj.target_fired])
    (out / "results.json").write_text(
        json.dumps(
            {"experiment": "E1", "seed": cfg["seed"], "n_valid": cfg["n_valid"],
             "summary": asdict(summary)},
            indent=2,
        ),
        encoding="utf-8",
    )
    _plot(summary, out / "e1.png")

    print(json.dumps(asdict(summary), indent=2))
    verdict = "ACCEPTED" if summary.accepted else "REJECTED"
    print(f"E1 {verdict} -> {out}/ (e1_cases.csv, e1_injections.csv, results.json, e1.png)")
    return 0 if summary.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
