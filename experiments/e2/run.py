"""E2 load driver: baseline (direct vLLM) vs gated (L2/L3 admission gate -> vLLM).

Run by experiments/e2/run.sh (which starts the gate + a vLLM port-forward first). Fires the same
offered load in both conditions and compares throughput/latency to show the control path is
orthogonal to the data path (SDD §10.2, R-2). Exit 0 iff accepted. Thin orchestration + I/O; the
metrics live in mqi.harness.e2 (unit-tested).
"""

from __future__ import annotations

import concurrent.futures as futures
import csv
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml

from mqi.harness.e2 import E2Summary, RequestSample, summarize, summarize_condition


def _post(url: str, payload: dict, timeout: float = 60.0) -> tuple[int, bytes]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()  # read() may raise IncompleteRead (HTTPException)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, exc.read()
        except (http.client.HTTPException, OSError):
            return exc.code, b""
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError):
        return 0, b""  # any transient network/timeout/truncation is a NON-success, not a crash


def _completion(vllm_url: str, model: str, prompt: str, max_tokens: int) -> bool:
    status, _ = _post(
        f"{vllm_url}/v1/completions",
        {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0},
    )
    return status == 200


def _run_condition(
    num_requests: int, concurrency: int, one: Callable[[int], RequestSample]
) -> tuple[list[RequestSample], float]:
    start = time.perf_counter()
    with futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        samples = list(pool.map(one, range(num_requests)))
    return samples, time.perf_counter() - start


def _plot(summary: E2Summary, path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4))
    conds = [summary.baseline, summary.gated]
    ax1.bar([c.condition for c in conds], [c.throughput_rps for c in conds],
            color=["#1f77b4", "#2ca02c"])
    ax1.set_ylabel("throughput (req/s)")
    ax1.set_title(f"throughput ratio={summary.throughput_ratio:.3f} (accepted={summary.accepted})")
    ax2.bar([c.condition for c in conds], [c.success_rate for c in conds],
            color=["#1f77b4", "#2ca02c"])
    ax2.set_ylabel("completeness (successes / offered)")
    ax2.set_ylim(0, 1.05)
    ax2.set_title(f"gate admit overhead={summary.gate_overhead_ms:.2f} ms")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    config_path = Path(args[0]) if args else Path(__file__).parent / "config.yaml"
    cfg = yaml.safe_load(config_path.read_text())
    out = Path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    vllm, gate = cfg["vllm_url"], cfg["gate_url"]
    model, prompt, max_tokens = cfg["model"], cfg["prompt"], cfg["max_tokens"]
    workload_id = cfg["workload_id"]
    num, conc = cfg["num_requests"], cfg["concurrency"]

    # ensure the gate admits under this (non-overload) load: give it ample L2 capacity. A failure
    # here means the load regime was never applied — abort loudly, don't report a bogus verdict.
    load_status, _ = _post(f"{gate}/load", {"slots": conc + 8, "min_service_ms": 1})
    if load_status != 200:
        print(f"E2 ERROR: gate /load returned {load_status}; load regime not set", file=sys.stderr)
        return 2

    # warm the model first so neither condition eats the cold-start cost.
    for _ in range(int(cfg.get("warmup", 0))):
        _completion(vllm, model, prompt, max_tokens)

    def baseline_one(i: int) -> RequestSample:
        t0 = time.perf_counter()
        ok = _completion(vllm, model, prompt, max_tokens)
        return RequestSample((time.perf_counter() - t0) * 1000.0, ok, admitted=None)

    def gated_one(i: int) -> RequestSample:
        t_admit = time.perf_counter()
        status, body = _post(f"{gate}/admit", {"workload_id": workload_id, "request_id": f"e2-{i}"})
        # only a SUCCESSFUL admit call has a real cost; a failed call (~0 ms) must not deflate it
        admit_ms = (time.perf_counter() - t_admit) * 1000.0 if status == 200 else None
        admitted = False
        if status == 200:
            try:
                admitted = json.loads(body).get("admission") == "admit"
            except (ValueError, AttributeError):
                admitted = False
        ok = admitted and _completion(vllm, model, prompt, max_tokens)
        total_ms = (time.perf_counter() - t_admit) * 1000.0
        return RequestSample(total_ms, ok, admitted=admitted, admit_latency_ms=admit_ms)

    # Alternate which condition runs first each round so run-order effects (GPU clock ramp, cache
    # warming) don't systematically favour one condition — removes the baseline-then-gated bias.
    rounds = max(1, int(cfg.get("rounds", 4)))
    per_round = max(1, num // rounds)
    base_samples: list[RequestSample] = []
    gated_samples: list[RequestSample] = []
    base_wall = gated_wall = 0.0
    for r in range(rounds):
        order = [("baseline", baseline_one), ("gated", gated_one)]
        if r % 2 == 1:
            order.reverse()
        for cond, one in order:
            samples, wall = _run_condition(per_round, conc, one)
            if cond == "baseline":
                base_samples += samples
                base_wall += wall
            else:
                gated_samples += samples
                gated_wall += wall
    baseline = summarize_condition("baseline", base_samples, base_wall)
    gated = summarize_condition("gated", gated_samples, gated_wall)
    summary = summarize(
        baseline, gated,
        min_ratio=cfg["min_ratio"],
        min_success_rate=cfg.get("min_success_rate", 0.97),
        min_admit_rate=cfg.get("min_admit_rate", 0.99),
    )

    with (out / "e2_conditions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["condition", "requests", "successes", "admitted", "success_rate", "admit_rate",
                    "throughput_rps", "p50_ms", "p99_ms", "admit_overhead_ms", "wall_seconds"])
        for c in (baseline, gated):
            overhead = None if c.admit_overhead_ms is None else round(c.admit_overhead_ms, 3)
            admit_rate = None if c.admit_rate is None else round(c.admit_rate, 4)
            w.writerow([c.condition, c.requests, c.successes, c.admitted, round(c.success_rate, 4),
                        admit_rate, round(c.throughput_rps, 3), round(c.p50_ms, 2),
                        round(c.p99_ms, 2), overhead, round(c.wall_seconds, 2)])
    (out / "results.json").write_text(
        json.dumps({"experiment": "E2", "config": cfg, "summary": asdict(summary)}, indent=2),
        encoding="utf-8",
    )
    _plot(summary, out / "e2.png")

    print(json.dumps(asdict(summary), indent=2))
    verdict = "ACCEPTED" if summary.accepted else "REJECTED"
    print(f"E2 {verdict}: ratio={summary.throughput_ratio:.3f} "
          f"(gated {gated.throughput_rps:.1f} vs baseline {baseline.throughput_rps:.1f} req/s), "
          f"completeness base={baseline.success_rate:.3f}/gated={gated.success_rate:.3f}, "
          f"admit overhead={summary.gate_overhead_ms:.2f} ms")
    return 0 if summary.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
