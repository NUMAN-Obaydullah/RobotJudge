"""Grader module for RobotJudge-CI.

Responsibilities:
  - Grade a single run (validate output, compute cost, assign status)
  - Aggregate per-case metrics (success_rate, best/mean/p95 cost, p95 runtime)
  - Aggregate suite-level metrics (PASS/FAIL gate, suite_score)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from robotjudge.schema import validate_path


# ---------------------------------------------------------------------------
# Per-run grading
# ---------------------------------------------------------------------------

def grade_run(
    run_record: dict[str, Any],
    case_data: dict,
    *,
    time_limit_ms: int | None = None,
    mem_limit_mb: int | None = None,
) -> dict[str, Any]:
    """Grade a single run and return a full run-record for results.json.

    Mutates *run_record* in place and also returns it.
    """
    case_id = run_record["case_id"]
    seed = run_record["seed"]
    runtime_ms = run_record.get("runtime_ms", 0)
    exit_code = run_record.get("exit_code", -1)
    timed_out = run_record.get("timed_out", False)

    # Start with defaults
    result: dict[str, Any] = {
        "case_id": case_id,
        "seed": seed,
        "status": "RTE",
        "valid": False,
        "collision": False,
        "reached_goal": False,
        "cost": 0.0,
        "path_length": 0.0,
        "runtime_ms": runtime_ms,
        "mem_mb": run_record.get("mem_mb", 0.0),
        "violations": [],
    }

    # Preserve log paths if present
    if "stdout_path" in run_record:
        result["stdout_path"] = run_record["stdout_path"]
    if "stderr_path" in run_record:
        result["stderr_path"] = run_record["stderr_path"]

    # TLE check
    if timed_out:
        result["status"] = "TLE"
        result["violations"] = ["Exceeded time limit"]
        return result

    # RTE check: non-zero exit or output file missing
    output_path = run_record.get("output_path")
    if exit_code != 0 or not output_path or not Path(output_path).exists():
        result["status"] = "RTE"
        result["violations"] = [
            f"Exit code {exit_code}" if exit_code != 0 else "No output file"
        ]
        return result

    # Parse output
    try:
        with open(output_path, "r", encoding="utf-8") as fh:
            path_data = json.load(fh)
    except Exception as exc:
        result["status"] = "RTE"
        result["violations"] = [f"Cannot parse output: {exc}"]
        return result

    # Validate
    valid, violations, metrics = validate_path(path_data, case_data)

    result["valid"] = valid
    result["violations"] = violations
    result["collision"] = metrics.get("collision", False)
    result["reached_goal"] = metrics.get("reached_goal", False)
    result["cost"] = metrics.get("cost", 0.0)
    result["path_length"] = metrics.get("path_length", 0.0)

    if not valid:
        result["status"] = "WA"
        return result

    # MLE check
    mem_mb = run_record.get("mem_mb", 0.0)
    if mem_limit_mb is not None and mem_mb > mem_limit_mb:
        result["status"] = "MLE"
        result["violations"] = [f"Memory {mem_mb:.1f} MB exceeds limit {mem_limit_mb} MB"]
        result["valid"] = False
        return result

    # TLE post-check (softer, for cases where subprocess didn't timeout but is over limit)
    effective_time_limit = time_limit_ms
    if effective_time_limit is not None and runtime_ms > effective_time_limit:
        result["status"] = "TLE"
        result["violations"] = [
            f"Runtime {runtime_ms} ms exceeds limit {effective_time_limit} ms"
        ]
        result["valid"] = False
        return result

    result["status"] = "AC"
    return result


# ---------------------------------------------------------------------------
# Per-case aggregation
# ---------------------------------------------------------------------------

def _percentile(values: list[float], p: float) -> float:
    """Simple percentile (nearest-rank method)."""
    if not values:
        return 0.0
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(math.ceil(p / 100.0 * len(values))) - 1))
    return values[k]


def aggregate_case(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute per-case aggregate metrics from a list of run-records for the same case."""
    if not runs:
        raise ValueError("No runs to aggregate")

    case_id = runs[0]["case_id"]
    total = len(runs)
    ac_runs = [r for r in runs if r["status"] == "AC"]
    ac_count = len(ac_runs)

    success_rate = ac_count / total
    failure_rate = 1.0 - success_rate

    ac_costs = [r["cost"] for r in ac_runs]
    all_runtimes = [r["runtime_ms"] for r in runs]

    if ac_costs:
        best_cost = min(ac_costs)
        mean_cost = sum(ac_costs) / len(ac_costs)
        p95_cost = _percentile(ac_costs, 95)
    else:
        best_cost = float("inf")
        mean_cost = float("inf")
        p95_cost = float("inf")

    best_runtime = min(all_runtimes) if all_runtimes else 0
    mean_runtime = int(sum(all_runtimes) / len(all_runtimes)) if all_runtimes else 0
    p95_runtime = int(_percentile([float(x) for x in all_runtimes], 95))

    return {
        "case_id": case_id,
        "success_rate": round(success_rate, 6),
        "failure_rate": round(failure_rate, 6),
        "best_cost": round(best_cost, 6),
        "mean_cost": round(mean_cost, 6),
        "p95_cost": round(p95_cost, 6),
        "best_runtime_ms": best_runtime,
        "mean_runtime_ms": mean_runtime,
        "p95_runtime_ms": p95_runtime,
    }


# ---------------------------------------------------------------------------
# Suite aggregation
# ---------------------------------------------------------------------------

def aggregate_suite(
    per_case: list[dict[str, Any]],
    all_runs: list[dict[str, Any]],
    *,
    success_gate: float = 0.95,
    lambda_runtime: float = 0.001,
    failure_penalty: float = 1_000_000.0,
    case_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute suite-level PASS/FAIL gate and score.

    Formula from docs/scoring.md §6.
    """
    total_runs = len(all_runs)
    ac_runs = sum(1 for r in all_runs if r["status"] == "AC")
    suite_success_rate = ac_runs / total_runs if total_runs > 0 else 0.0

    status = "PASS" if suite_success_rate >= success_gate else "FAIL"

    # Suite score
    score = 0.0
    for pc in per_case:
        w = 1.0
        if case_weights:
            w = case_weights.get(pc["case_id"], 1.0)
        p95c = pc["p95_cost"] if math.isfinite(pc["p95_cost"]) else 1e9
        score += w * p95c
        score += lambda_runtime * w * pc["p95_runtime_ms"]
        score += failure_penalty * w * pc["failure_rate"]

    all_runtimes = [r["runtime_ms"] for r in all_runs]
    p95_runtime = int(_percentile([float(x) for x in all_runtimes], 95)) if all_runtimes else 0

    notes_parts: list[str] = []
    notes_parts.append(f"gate_threshold={success_gate}")
    notes_parts.append(f"lambda={lambda_runtime}")
    notes_parts.append(f"failure_penalty={failure_penalty}")

    return {
        "status": status,
        "suite_success_rate": round(suite_success_rate, 6),
        "suite_score": round(score, 4),
        "p95_runtime_ms": p95_runtime,
        "notes": "; ".join(notes_parts),
    }
