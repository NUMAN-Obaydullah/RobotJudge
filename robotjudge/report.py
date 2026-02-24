"""Report generator for RobotJudge-CI.

Produces:
  - ``report.md``  — GitHub-renderable summary (PASS/FAIL, score, per-case table)
  - ``results.json`` — full machine-readable metrics matching results.schema.json
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def generate_results_json(
    suite_id: str,
    submission_name: str,
    submission_entrypoint: str,
    seed_policy: dict,
    runs: list[dict[str, Any]],
    per_case: list[dict[str, Any]],
    suite_agg: dict[str, Any],
    *,
    commit: str | None = None,
    environment: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build the full results.json structure."""
    if run_id is None:
        # Deterministic run_id from inputs
        id_src = f"{suite_id}:{submission_name}:{json.dumps(seed_policy, sort_keys=True)}"
        run_id = hashlib.sha256(id_src.encode()).hexdigest()[:12]

    submission: dict[str, Any] = {
        "name": submission_name,
        "entrypoint": submission_entrypoint,
    }
    if commit:
        submission["commit"] = commit
    if environment:
        submission["environment"] = environment

    # Sanitise runs — ensure only schema-allowed keys, handle inf/nan
    clean_runs: list[dict[str, Any]] = []
    allowed_run_keys = {
        "case_id", "seed", "status", "valid", "collision", "reached_goal",
        "cost", "path_length", "runtime_ms", "mem_mb", "violations",
        "stdout_path", "stderr_path",
    }
    for r in runs:
        cr: dict[str, Any] = {}
        for k in allowed_run_keys:
            if k in r:
                v = r[k]
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    v = 0.0
                cr[k] = v
        clean_runs.append(cr)

    # Sanitise per_case — handle inf
    clean_per_case: list[dict[str, Any]] = []
    for pc in per_case:
        cpc = dict(pc)
        for k in ("best_cost", "mean_cost", "p95_cost"):
            if isinstance(cpc.get(k), float) and (math.isinf(cpc[k]) or math.isnan(cpc[k])):
                cpc[k] = 1e9
        clean_per_case.append(cpc)

    return {
        "version": "1.0",
        "run_id": run_id,
        "suite_id": suite_id,
        "submission": submission,
        "seed_policy": seed_policy,
        "runs": clean_runs,
        "per_case": clean_per_case,
        "suite": suite_agg,
    }


def generate_report_md(
    suite_agg: dict[str, Any],
    per_case: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    *,
    suite_id: str = "",
    submission_name: str = "",
) -> str:
    """Generate a GitHub-renderable Markdown report."""
    lines: list[str] = []
    status = suite_agg["status"]
    emoji = "✅" if status == "PASS" else "❌"

    lines.append(f"# RobotJudge Report {emoji} **{status}**")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Suite | `{suite_id}` |")
    lines.append(f"| Submission | `{submission_name}` |")
    lines.append(f"| Success Rate | {suite_agg['suite_success_rate']:.2%} |")
    lines.append(f"| Suite Score | {suite_agg['suite_score']:.2f} |")
    lines.append(f"| P95 Runtime | {suite_agg['p95_runtime_ms']} ms |")
    if suite_agg.get("notes"):
        lines.append(f"| Parameters | {suite_agg['notes']} |")
    lines.append("")

    # Per-case table
    lines.append("## Per-Case Results")
    lines.append("")
    lines.append("| Case | Success | Fail | Best Cost | Mean Cost | P95 Cost | P95 RT (ms) |")
    lines.append("|------|---------|------|-----------|-----------|----------|-------------|")
    for pc in per_case:
        bc = f"{pc['best_cost']:.1f}" if math.isfinite(pc["best_cost"]) else "∞"
        mc = f"{pc['mean_cost']:.1f}" if math.isfinite(pc["mean_cost"]) else "∞"
        p95c = f"{pc['p95_cost']:.1f}" if math.isfinite(pc["p95_cost"]) else "∞"
        lines.append(
            f"| `{pc['case_id']}` "
            f"| {pc['success_rate']:.0%} "
            f"| {pc['failure_rate']:.0%} "
            f"| {bc} | {mc} | {p95c} "
            f"| {pc['p95_runtime_ms']} |"
        )
    lines.append("")

    # Worst cases
    failures = [pc for pc in per_case if pc["failure_rate"] > 0]
    if failures:
        failures.sort(key=lambda x: x["failure_rate"], reverse=True)
        lines.append("## Worst Cases")
        lines.append("")
        for pc in failures[:10]:
            case_runs = [r for r in runs if r["case_id"] == pc["case_id"]]
            bad_runs = [r for r in case_runs if r["status"] != "AC"]
            reasons = set()
            for r in bad_runs:
                reasons.add(r["status"])
                for v in r.get("violations", []):
                    reasons.add(v[:80])
            lines.append(
                f"- **`{pc['case_id']}`**: {pc['failure_rate']:.0%} failure "
                f"(reasons: {', '.join(sorted(reasons))})"
            )
        lines.append("")

    # Seed robustness summary
    lines.append("## Seed Robustness")
    lines.append("")
    robust = [pc for pc in per_case if pc["success_rate"] == 1.0]
    lines.append(
        f"- {len(robust)}/{len(per_case)} cases passed across all seeds"
    )
    if per_case:
        min_sr = min(pc["success_rate"] for pc in per_case)
        lines.append(f"- Minimum per-case success rate: {min_sr:.0%}")
    lines.append("")

    return "\n".join(lines)


def write_report(
    report_dir: str | Path,
    results_data: dict[str, Any],
    report_md: str,
) -> tuple[Path, Path]:
    """Write results.json and report.md to *report_dir*."""
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    results_path = report_dir / "results.json"
    with open(results_path, "w", encoding="utf-8") as fh:
        json.dump(results_data, fh, indent=2, sort_keys=True)

    report_path = report_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    return results_path, report_path
