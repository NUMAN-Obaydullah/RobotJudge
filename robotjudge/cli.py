"""RobotJudge-CI command-line interface.

Subcommands:
  generate   — generate testcases from a suite config
  run        — run submission(s) across a suite, grade, and produce report
  validate   — validate a single case or path file
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from robotjudge import __version__
from robotjudge.generator import generate_suite, load_suite_config
from robotjudge.grader import aggregate_case, aggregate_suite, grade_run
from robotjudge.report import (
    generate_report_md,
    generate_results_json,
    write_report,
)
from robotjudge.runner import run_suite
from robotjudge.schema import validate_case, validate_path_schema, validate_case_schema


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

def cmd_generate(args: argparse.Namespace) -> int:
    config = Path(args.config)
    output = Path(args.out)
    seed = args.seed

    print(f"[generate] config={config}  out={output}  seed={seed}")
    cases = generate_suite(config, output, master_seed=seed)
    print(f"[generate] {len(cases)} testcases generated under {output}")
    return 0


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def _parse_seeds(seeds_str: str) -> list[int]:
    """Parse '0..99' or '0,1,2,3' into a list of ints."""
    if ".." in seeds_str:
        parts = seeds_str.split("..")
        return list(range(int(parts[0]), int(parts[1]) + 1))
    return [int(s.strip()) for s in seeds_str.split(",")]


def cmd_run(args: argparse.Namespace) -> int:
    suite_dir = Path(args.suite)
    submission = Path(args.submission)
    report_dir = Path(args.report_dir)
    seeds = _parse_seeds(args.seeds)
    time_limit = args.time_limit

    print(f"[run] suite={suite_dir}  submission={submission}")
    print(f"[run] seeds={seeds[0]}..{seeds[-1]} ({len(seeds)} seeds)")

    # Run all (case, seed) pairs
    records = run_suite(
        submission,
        suite_dir,
        report_dir / "logs",
        seeds=seeds,
        time_limit_ms=time_limit,
    )

    # Load case data for grading
    case_files = sorted(suite_dir.rglob("case.json"))
    case_data_map: dict[str, dict] = {}
    for cf in case_files:
        with open(cf, "r", encoding="utf-8") as fh:
            cd = json.load(fh)
        case_data_map[cd["id"]] = cd

    # Grade each run
    graded_runs: list[dict] = []
    for rec in records:
        cd = case_data_map.get(rec["case_id"])
        if cd is None:
            rec["status"] = "RTE"
            rec["valid"] = False
            rec["violations"] = [f"Case {rec['case_id']} not found"]
            rec["cost"] = 0.0
            rec["path_length"] = 0.0
            rec["collision"] = False
            rec["reached_goal"] = False
            graded_runs.append(rec)
            continue
        graded = grade_run(
            rec, cd,
            time_limit_ms=cd.get("limits", {}).get("time_ms", time_limit),
        )
        graded_runs.append(graded)

    # Per-case aggregation
    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in graded_runs:
        by_case[r["case_id"]].append(r)

    per_case = [aggregate_case(runs) for runs in by_case.values()]
    per_case.sort(key=lambda x: x["case_id"])

    # Load suite config for scoring params
    # Try to find a matching config
    config_path = suite_dir.parent / "configs" / "public_suite.yaml"
    if not config_path.exists():
        # Try relative to project root via naming convention
        config_path = Path("configs") / "public_suite.yaml"

    scoring_params: dict = {}
    suite_id = "unknown"
    seed_policy: dict = {"type": "range", "start": seeds[0], "count": len(seeds)}
    if config_path.exists():
        cfg = load_suite_config(config_path)
        suite_id = cfg.get("suite_id", suite_id)
        rpt = cfg.get("reporting", {})
        scoring_params = {
            "success_gate": rpt.get("success_gate", 0.95),
            "lambda_runtime": rpt.get("lambda_runtime", 0.001),
            "failure_penalty": rpt.get("failure_penalty", 1_000_000.0),
        }
        sp = cfg.get("seed_policy")
        if sp:
            seed_policy = sp

    suite_agg = aggregate_suite(
        per_case,
        graded_runs,
        **scoring_params,
    )

    # Build results.json
    results_data = generate_results_json(
        suite_id=suite_id,
        submission_name=submission.stem,
        submission_entrypoint=str(submission),
        seed_policy=seed_policy,
        runs=graded_runs,
        per_case=per_case,
        suite_agg=suite_agg,
    )

    # Build report.md
    report_md = generate_report_md(
        suite_agg,
        per_case,
        graded_runs,
        suite_id=suite_id,
        submission_name=submission.stem,
    )

    # Write outputs
    results_path, report_path = write_report(report_dir, results_data, report_md)

    status_tag = "[PASS]" if suite_agg["status"] == "PASS" else "[FAIL]"
    print(f"\n{status_tag}  Suite status: {suite_agg['status']}")
    print(f"   Success rate: {suite_agg['suite_success_rate']:.2%}")
    print(f"   Suite score:  {suite_agg['suite_score']:.2f}")
    print(f"\n   Results: {results_path}")
    print(f"   Report:  {report_path}")

    return 0 if suite_agg["status"] == "PASS" else 1


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    target = Path(args.file)
    with open(target, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if args.type == "case":
        errors = validate_case(data)
    elif args.type == "path":
        errors = validate_path_schema(data)
    elif args.type == "auto":
        # Auto-detect
        if "grid" in data:
            errors = validate_case(data)
        elif "path" in data:
            errors = validate_path_schema(data)
        else:
            print("[validate] Cannot auto-detect file type (no 'grid' or 'path' key)")
            return 1
    else:
        print(f"[validate] Unknown type: {args.type}")
        return 1

    if errors:
        print(f"[validate] INVALID -- {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("[validate] VALID [OK]")
        return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="robotjudge",
        description="RobotJudge-CI: auto-grading judge for GridPath",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    # generate
    gen = sub.add_parser("generate", help="Generate testcases from config")
    gen.add_argument("--config", required=True, help="Path to suite config YAML")
    gen.add_argument("--out", required=True, help="Output directory for testcases")
    gen.add_argument("--seed", type=int, default=42, help="Master seed (default 42)")

    # run
    run = sub.add_parser("run", help="Run submission, grade, and report")
    run.add_argument("--suite", required=True, help="Path to testcases directory")
    run.add_argument("--submission", required=True, help="Path to submission script")
    run.add_argument("--seeds", default="0..4", help="Seeds, e.g. '0..99' or '0,1,2'")
    run.add_argument("--report-dir", default="reports", help="Output dir for reports")
    run.add_argument("--time-limit", type=int, default=30000, help="Time limit per run (ms)")

    # validate
    val = sub.add_parser("validate", help="Validate a case or path file")
    val.add_argument("file", help="Path to JSON file")
    val.add_argument("--type", choices=["case", "path", "auto"], default="auto")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    handlers = {
        "generate": cmd_generate,
        "run": cmd_run,
        "validate": cmd_validate,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
