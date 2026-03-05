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
    sandbox: bool = False,
) -> dict[str, Any]:
    """Run a single (case, seed) invocation.

    Returns a partial run-record dict with keys:
      case_id, seed, exit_code, runtime_ms, stdout_path, stderr_path, output_path
    """
    submission = Path(submission).resolve()
    case_path = Path(case_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read case_id
    with open(case_path, "r", encoding="utf-8") as fh:
        case_data = json.load(fh)
    case_id = case_data["id"]

    # Output file for the solver
    out_path = output_dir / f"{case_id}_seed{seed}_path.json"
    stdout_path = output_dir / f"{case_id}_seed{seed}_stdout.txt"
    stderr_path = output_dir / f"{case_id}_seed{seed}_stderr.txt"

    timeout_s = time_limit_ms / 1000.0

    if sandbox:
        timeout_s += 3.0  # docker startup grace period
        # Resolve paths to absolutes for Docker volume mounting
        mem = mem_limit_mb if mem_limit_mb is not None else 256
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--cpus", "1",
            "-m", f"{mem}m",
            "-v", f"{case_path}:/data/case.json:ro",
            "-v", f"{submission}:/src/solver.py:ro",
            "-v", f"{output_dir}:/out",
            "rj-sandbox",
            "/src/solver.py",
            "--case", "/data/case.json",
            "--seed", str(seed),
            "--out", f"/out/{out_path.name}",
        ]
    else:
        py = python_exe or sys.executable
        cmd = [
            py,
            str(submission),
            "--case", str(case_path),
            "--seed", str(seed),
            "--out", str(out_path),
        ]

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
        import psutil
        t0 = time.perf_counter()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        
        try:
            p = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            p = None
            
        peak_memory_mb = 0.0
        timed_out_flag = False
        
        while proc.poll() is None:
            if p:
                try:
                    mem = p.memory_info().rss / (1024 * 1024)
                    if mem > peak_memory_mb:
                        peak_memory_mb = mem
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            if time.perf_counter() - t0 > timeout_s:
                proc.kill()
                timed_out_flag = True
                break
                
            time.sleep(0.01)
            
        t1 = time.perf_counter()
        stdout_data, stderr_data = proc.communicate()
        
        record["mem_mb"] = peak_memory_mb
        
        if timed_out_flag:
            raise subprocess.TimeoutExpired(cmd, timeout_s, output=stdout_data, stderr=stderr_data)

        runtime_ms = int((t1 - t0) * 1000)
        if sandbox:
            runtime_ms = max(0, runtime_ms - 1600)  # compensate for docker spinup overhead
        
        record["runtime_ms"] = runtime_ms
        record["exit_code"] = proc.returncode

        # Write stdout/stderr
        stdout_path.write_text(stdout_data or "", encoding="utf-8")
        stderr_path.write_text(stderr_data or "", encoding="utf-8")

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
    sandbox: bool = False,
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
                sandbox=sandbox,
            )
            records.append(rec)

    return records
