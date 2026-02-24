"""Execution harness for RobotJudge-CI.

Runs a submission CLI per (case, seed) pair, capturing:
  - exit code, stdout, stderr
  - wall-clock runtime_ms
  - (optional) peak memory usage
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def run_single(
    submission: str | Path,
    case_path: str | Path,
    seed: int,
    output_dir: str | Path,
    *,
    time_limit_ms: int = 30_000,
    mem_limit_mb: int | None = None,
    python_exe: str | None = None,
) -> dict[str, Any]:
    """Run a single (case, seed) invocation.

    Returns a partial run-record dict with keys:
      case_id, seed, exit_code, runtime_ms, stdout_path, stderr_path, output_path
    """
    submission = Path(submission)
    case_path = Path(case_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read case_id
    with open(case_path, "r", encoding="utf-8") as fh:
        case_data = json.load(fh)
    case_id = case_data["id"]

    # Output file for the solver
    out_path = output_dir / f"{case_id}_seed{seed}_path.json"
    stdout_path = output_dir / f"{case_id}_seed{seed}_stdout.txt"
    stderr_path = output_dir / f"{case_id}_seed{seed}_stderr.txt"

    py = python_exe or sys.executable
    cmd = [
        py,
        str(submission),
        "--case", str(case_path),
        "--seed", str(seed),
        "--out", str(out_path),
    ]

    timeout_s = time_limit_ms / 1000.0

    record: dict[str, Any] = {
        "case_id": case_id,
        "seed": seed,
        "runtime_ms": 0,
        "exit_code": -1,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "output_path": str(out_path),
        "timed_out": False,
    }

    try:
        t0 = time.perf_counter()
        result = subprocess.run(
            cmd,
            timeout=timeout_s,
            capture_output=True,
            text=True,
        )
        t1 = time.perf_counter()

        record["runtime_ms"] = int((t1 - t0) * 1000)
        record["exit_code"] = result.returncode

        # Write stdout/stderr
        stdout_path.write_text(result.stdout or "", encoding="utf-8")
        stderr_path.write_text(result.stderr or "", encoding="utf-8")

    except subprocess.TimeoutExpired as e:
        record["runtime_ms"] = time_limit_ms
        record["timed_out"] = True
        record["exit_code"] = -1
        stdout_path.write_text(
            (e.stdout or b"").decode("utf-8", errors="replace"),
            encoding="utf-8",
        )
        stderr_path.write_text(
            (e.stderr or b"").decode("utf-8", errors="replace"),
            encoding="utf-8",
        )
    except Exception as exc:
        record["exit_code"] = -1
        stderr_path.write_text(str(exc), encoding="utf-8")
        stdout_path.write_text("", encoding="utf-8")

    return record


def run_suite(
    submission: str | Path,
    suite_dir: str | Path,
    output_dir: str | Path,
    *,
    seeds: list[int] | None = None,
    seed_start: int = 0,
    seed_count: int = 5,
    time_limit_ms: int = 30_000,
    mem_limit_mb: int | None = None,
    python_exe: str | None = None,
) -> list[dict[str, Any]]:
    """Run a submission across every case in *suite_dir* and every seed.

    Discovers cases by finding all ``case.json`` files recursively.
    Returns a list of run-record dicts.
    """
    suite_dir = Path(suite_dir)
    case_files = sorted(suite_dir.rglob("case.json"))
    if not case_files:
        raise FileNotFoundError(f"No case.json found under {suite_dir}")

    if seeds is None:
        seeds = list(range(seed_start, seed_start + seed_count))

    records: list[dict[str, Any]] = []
    for case_path in case_files:
        # Read case to get per-case limits
        with open(case_path, "r", encoding="utf-8") as fh:
            case_data = json.load(fh)
        case_limits = case_data.get("limits", {})
        effective_time = min(
            time_limit_ms,
            case_limits.get("time_ms", time_limit_ms),
        )

        for seed in seeds:
            rec = run_single(
                submission,
                case_path,
                seed,
                output_dir,
                time_limit_ms=effective_time,
                mem_limit_mb=mem_limit_mb,
                python_exe=python_exe,
            )
            records.append(rec)

    return records
