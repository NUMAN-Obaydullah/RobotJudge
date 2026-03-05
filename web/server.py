"""RobotJudge-CI Web Server — AOJ v3 Style Interface.

Run with:  python web/server.py
Then open: http://localhost:8000
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import random as _random_mod
import subprocess
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse
import uvicorn

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ensure project root is importable so `web.database` resolves
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.database import (
    init_db, get_db,
    get_all_testcases, get_testcase,
    get_all_result_sets, get_result_set_detail, get_case_results,
    get_all_solvers, get_solver_code,
    upsert_job, get_job, get_all_jobs,
    Solver, ResultSet, Run, PerCaseStat, PathRecord,
)
TESTCASES_DIR = PROJECT_ROOT / "testcases" / "public"
REPORTS_DIR = PROJECT_ROOT / "reports"
SUBMISSIONS_DIR = PROJECT_ROOT / "submissions"
BASELINES_DIR = PROJECT_ROOT / "baselines"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "judge.yml"

app = FastAPI(title="RobotJudge-CI", version="1.0")


@app.on_event("startup")
def startup_event():
    """Initialize database tables on startup."""
    init_db()


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# Pages (serve HTML)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def page_index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

@app.get("/problem/{case_id}", response_class=HTMLResponse)
async def page_problem(case_id: str):
    return (STATIC_DIR / "problem.html").read_text(encoding="utf-8")

@app.get("/submit", response_class=HTMLResponse)
async def page_submit():
    return (STATIC_DIR / "submit.html").read_text(encoding="utf-8")

@app.get("/status", response_class=HTMLResponse)
async def page_status():
    return (STATIC_DIR / "status.html").read_text(encoding="utf-8")

@app.get("/ci", response_class=HTMLResponse)
async def page_ci():
    return (STATIC_DIR / "ci.html").read_text(encoding="utf-8")

@app.get("/report", response_class=HTMLResponse)
async def page_report():
    return (STATIC_DIR / "report.html").read_text(encoding="utf-8")

@app.get("/manual", response_class=HTMLResponse)
async def page_manual():
    return (STATIC_DIR / "manual.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# API: Version
# ---------------------------------------------------------------------------

import robotjudge
@app.get("/api/version")
async def api_version():
    return {"version": robotjudge.__version__ + " (Sandbox & Vis)", "name": "RobotJudge-CI"}


# ---------------------------------------------------------------------------
# API — Cases
# ---------------------------------------------------------------------------

@app.get("/api/cases")
async def api_cases():
    """List all cases (summary only, no grids)."""
    db = get_db()
    try:
        rows = get_all_testcases(db, include_grid=False)
        # Add derived fields for frontend compatibility
        for r in rows:
            meta = r.get("meta") or {}
            r["difficulty"] = meta.get("difficulty", meta.get("tier", r.get("tier", "")))
            r["has_cell_cost"] = False
        return rows
    finally:
        db.close()


@app.get("/api/case/{case_id}")
async def api_case(case_id: str):
    """Get full case data including grid."""
    db = get_db()
    try:
        data = get_testcase(db, case_id)
        if not data:
            raise HTTPException(404, f"Case '{case_id}' not found")
        return data
    finally:
        db.close()


# ---------------------------------------------------------------------------
# API — Results
# ---------------------------------------------------------------------------

@app.get("/api/results")
async def api_results():
    """List all available result sets."""
    db = get_db()
    try:
        return get_all_result_sets(db)
    finally:
        db.close()


@app.get("/api/results/{name}")
async def api_result_detail(name: str):
    """Get full results.json for a named report."""
    db = get_db()
    try:
        data = get_result_set_detail(db, name)
        if not data:
            raise HTTPException(404, f"Result '{name}' not found")
        return data
    finally:
        db.close()


@app.get("/api/results/{name}/report")
async def api_result_report(name: str):
    """Get rendered report.md content."""
    # Reports are still on disk (markdown is not in DB)
    rp = REPORTS_DIR / name / "report.md"
    if not rp.exists():
        raise HTTPException(404, f"Report '{name}' not found")
    return {"content": rp.read_text(encoding="utf-8")}


@app.get("/api/results/{name}/logs")
async def api_result_logs(name: str):
    """Download the raw artifact logs as a ZIP file."""
    logs_dir = REPORTS_DIR / name / "logs"
    if not logs_dir.exists():
        raise HTTPException(404, f"Logs for '{name}' not found")
    
    zip_path = REPORTS_DIR / name / "logs.zip"
    # Create the zip if it hasn't been created yet
    if not zip_path.exists():
        shutil.make_archive(str(logs_dir), "zip", str(logs_dir))
        
    return FileResponse(zip_path, filename=f"{name}_logs.zip")



# ---------------------------------------------------------------------------
# API — Path results for a case (from baseline)
# ---------------------------------------------------------------------------

@app.get("/api/results/{name}/case/{case_id}")
async def api_case_results(name: str, case_id: str):
    """Get per-run results for a specific case from a results set."""
    db = get_db()
    try:
        data = get_case_results(db, name, case_id)
        if data is None:
            raise HTTPException(404, f"Result '{name}' not found")
        return data
    finally:
        db.close()


# ---------------------------------------------------------------------------
# API — Solver Code Viewer
# ---------------------------------------------------------------------------

@app.get("/api/solvers")
async def api_solvers():
    """List all available solver files (baselines + submissions)."""
    db = get_db()
    try:
        return get_all_solvers(db)
    finally:
        db.close()


@app.get("/api/solver/{solver_type}/{solver_name}")
async def api_solver_code(solver_type: str, solver_name: str):
    """Get the source code of a solver."""
    db = get_db()
    try:
        # DB 'name' column stores the stem for baselines.
        # Be resilient if someone sends the full filename.
        search_name = solver_name
        if solver_type == "baseline" and search_name.endswith(".py"):
            search_name = search_name[:-3]

        code = get_solver_code(db, solver_type, search_name)
        if code is None:
            raise HTTPException(404, f"Solver '{solver_name}' not found")
        return {
            "name": solver_name,
            "filename": solver_name + ".py" if not solver_name.endswith(".py") else solver_name,
            "type": solver_type,
            "code": code,
            "lines": len(code.splitlines()),
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# API — CI Pipeline
# ---------------------------------------------------------------------------

@app.get("/api/ci/workflow")
async def api_ci_workflow():
    """Get the CI workflow YAML source."""
    if CI_WORKFLOW.exists():
        return {
            "path": str(CI_WORKFLOW.relative_to(PROJECT_ROOT)),
            "content": CI_WORKFLOW.read_text(encoding="utf-8"),
        }
    raise HTTPException(404, "CI workflow not found")


# ---------------------------------------------------------------------------
# API — Baselines listing
# ---------------------------------------------------------------------------

@app.get("/api/baselines")
async def api_baselines():
    """List available baseline solver files."""
    solvers = []
    if BASELINES_DIR.exists():
        for f in sorted(BASELINES_DIR.glob("*.py")):
            solvers.append({
                "name": f.stem,
                "filename": f.name,
                "path": str(f),
            })
    return solvers


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------

def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_cmd(cmd, timeout=120):
    """Helper to run a subprocess and capture output."""
    proc = subprocess.run(
        cmd, cwd=str(PROJECT_ROOT),
        capture_output=True, text=True, timeout=timeout,
    )
    return proc


# ---------------------------------------------------------------------------
# API — Full CI Pipeline (SSE streaming)
# ---------------------------------------------------------------------------

@app.get("/api/ci/run-pipeline")
async def api_ci_run_pipeline():
    """Run the full CI pipeline locally, streaming progress via SSE."""

    async def _stream() -> AsyncGenerator[str, None]:
        stages = []

        # Stage 1: Testcase Generation
        yield _sse_event("stage", {"name": "Testcase Generation", "status": "running", "index": 0})
        stage = {"name": "Testcase Generation", "status": "running", "output": ""}
        try:
            ci_out = PROJECT_ROOT / "testcases" / "ci_gen"
            proc = _run_cmd([
                "python", "-m", "robotjudge.cli", "generate",
                "--config", str(PROJECT_ROOT / "configs" / "public_suite.yaml"),
                "--out", str(ci_out),
                "--seed", "42",
            ])
            stage["output"] = proc.stdout + proc.stderr
            stage["status"] = "pass" if proc.returncode == 0 else "fail"
            if ci_out.exists():
                count = len(list(ci_out.rglob("case.json")))
                stage["results"] = {"cases_generated": count}
        except Exception as e:
            stage["output"] = str(e)
            stage["status"] = "error"
        stages.append(stage)
        yield _sse_event("stage_done", stage)

        # Stage 2: Schema Validation
        yield _sse_event("stage", {"name": "Schema Validation", "status": "running", "index": 1})
        stage = {"name": "Schema Validation", "status": "running", "output": ""}
        try:
            case_files = sorted(TESTCASES_DIR.rglob("case.json"))
            validated = 0
            errors = 0
            output_lines = []
            for cf in case_files[:20]:
                proc = _run_cmd([
                    "python", "-m", "robotjudge.cli", "validate",
                    str(cf), "--type", "case",
                ], timeout=10)
                name = cf.parent.name
                if proc.returncode == 0:
                    validated += 1
                    output_lines.append(f"[OK] {name}")
                else:
                    errors += 1
                    output_lines.append(f"[FAIL] {name}: {proc.stdout.strip()}")
                # Stream partial validation progress
                if validated % 5 == 0:
                    yield _sse_event("log", {"stage": "Schema Validation", "line": f"Validated {validated}/{len(case_files)} cases..."})

            remaining = len(case_files) - 20
            if remaining > 0:
                output_lines.append(f"... and {remaining} more cases (skipped for speed)")
            stage["output"] = "\n".join(output_lines)
            stage["status"] = "pass" if errors == 0 else "fail"
            stage["results"] = {"validated": validated, "errors": errors, "total": len(case_files)}
        except Exception as e:
            stage["output"] = str(e)
            stage["status"] = "error"
        stages.append(stage)
        yield _sse_event("stage_done", stage)

        # Stage 3: Unit Tests
        yield _sse_event("stage", {"name": "Unit Tests", "status": "running", "index": 2})
        stage = {"name": "Unit Tests", "status": "running", "output": ""}
        try:
            proc = _run_cmd(["python", "-m", "pytest", "tests/", "-v", "--tb=short"], timeout=120)
            stage["output"] = proc.stdout + proc.stderr
            stage["status"] = "pass" if proc.returncode == 0 else "fail"
            lines = proc.stdout.split("\n")
            passed = sum(1 for l in lines if " PASSED" in l)
            failed = sum(1 for l in lines if " FAILED" in l)
            stage["results"] = {"passed": passed, "failed": failed, "total": passed + failed}
        except subprocess.TimeoutExpired:
            stage["output"] = "Tests timed out after 120s"
            stage["status"] = "error"
        except Exception as e:
            stage["output"] = str(e)
            stage["status"] = "error"
        stages.append(stage)
        yield _sse_event("stage_done", stage)

        # Stage 4: Baseline Judge Run
        yield _sse_event("stage", {"name": "Baseline Judge Run", "status": "running", "index": 3})
        stage = {"name": "Baseline Judge Run", "status": "running", "output": ""}
        try:
            report_dir = REPORTS_DIR / "ci_check"
            proc = _run_cmd([
                "python", "-m", "robotjudge.cli", "run",
                "--suite", str(TESTCASES_DIR),
                "--submission", str(BASELINES_DIR / "astar.py"),
                "--seeds", "0",
                "--report-dir", str(report_dir),
            ], timeout=180)
            stage["output"] = proc.stdout + proc.stderr
            stage["status"] = "pass" if proc.returncode == 0 else "fail"
            rj = report_dir / "results.json"
            if rj.exists():
                with open(rj, "r") as f:
                    results = json.load(f)
                suite = results.get("suite", {})
                stage["results"] = {
                    "status": suite.get("status"),
                    "success_rate": suite.get("suite_success_rate"),
                    "score": suite.get("suite_score"),
                    "total_runs": len(results.get("runs", [])),
                }
        except subprocess.TimeoutExpired:
            stage["output"] = "Judge run timed out after 180s"
            stage["status"] = "error"
        except Exception as e:
            stage["output"] = str(e)
            stage["status"] = "error"
        stages.append(stage)
        yield _sse_event("stage_done", stage)

        # Stage 5: Report & Artifacts
        yield _sse_event("stage", {"name": "Report & Artifacts", "status": "running", "index": 4})
        stage = {"name": "Report & Artifacts", "status": "running", "output": ""}
        try:
            report_dir = REPORTS_DIR / "ci_check"
            rj = report_dir / "results.json"
            rm = report_dir / "report.md"
            output_lines = []
            if rj.exists():
                output_lines.append(f"[OK] results.json ({rj.stat().st_size:,} bytes)")
            else:
                output_lines.append("[FAIL] results.json not found")
            if rm.exists():
                output_lines.append(f"[OK] report.md ({rm.stat().st_size:,} bytes)")
            else:
                output_lines.append("[FAIL] report.md not found")
            logs_dir = report_dir / "logs"
            if logs_dir.exists():
                log_count = len(list(logs_dir.iterdir()))
                output_lines.append(f"[OK] logs/ ({log_count} files)")
            else:
                output_lines.append("[INFO] logs/ directory not found")
            stage["output"] = "\n".join(output_lines)
            stage["status"] = "pass" if rj.exists() and rm.exists() else "fail"
        except Exception as e:
            stage["output"] = str(e)
            stage["status"] = "error"
        stages.append(stage)
        yield _sse_event("stage_done", stage)

        # Stage 6: Determinism Gate
        yield _sse_event("stage", {"name": "Determinism Gate", "status": "running", "index": 5})
        stage = {"name": "Determinism Gate", "status": "running", "output": ""}
        try:
            det_script = SCRIPTS_DIR / "check_determinism.py"
            if det_script.exists():
                r1 = REPORTS_DIR / "ci_det1"
                r2 = REPORTS_DIR / "ci_det2"
                yield _sse_event("log", {"stage": "Determinism Gate", "line": "Running solver pass 1..."})
                out1 = _run_cmd([
                    "python", "-m", "robotjudge.cli", "run",
                    "--suite", str(TESTCASES_DIR),
                    "--submission", str(BASELINES_DIR / "astar.py"),
                    "--seeds", "0",
                    "--report-dir", str(r1),
                ], timeout=180)
                yield _sse_event("log", {"stage": "Determinism Gate", "line": "Running solver pass 2..."})
                out2 = _run_cmd([
                    "python", "-m", "robotjudge.cli", "run",
                    "--suite", str(TESTCASES_DIR),
                    "--submission", str(BASELINES_DIR / "astar.py"),
                    "--seeds", "0",
                    "--report-dir", str(r2),
                ], timeout=180)
                yield _sse_event("log", {"stage": "Determinism Gate", "line": "Comparing results..."})
                proc = _run_cmd([
                    "python", str(det_script),
                    str(r1 / "results.json"),
                    str(r2 / "results.json"),
                ], timeout=30)
                stage["output"] = (
                    "=== Run 1 ===\n" + out1.stdout[-200:] + "\n"
                    "=== Run 2 ===\n" + out2.stdout[-200:] + "\n"
                    "=== Determinism Check ===\n" + proc.stdout + proc.stderr
                )
                stage["status"] = "pass" if proc.returncode == 0 else "fail"
            else:
                stage["output"] = "Determinism script not found at scripts/check_determinism.py"
                stage["status"] = "skip"
        except subprocess.TimeoutExpired:
            stage["output"] = "Determinism check timed out"
            stage["status"] = "error"
        except Exception as e:
            stage["output"] = str(e)
            stage["status"] = "error"
        stages.append(stage)
        yield _sse_event("stage_done", stage)

        # Final done event
        overall = "pass" if all(s["status"] in ("pass", "skip") for s in stages) else "fail"
        yield _sse_event("done", {
            "pipeline": "RobotJudge CI",
            "timestamp": datetime.datetime.now().isoformat(),
            "stages": stages,
            "overall": overall,
        })

    return StreamingResponse(_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# API — Custom CI Run (SSE streaming)
# ---------------------------------------------------------------------------

@app.get("/api/ci/run-custom")
async def api_ci_run_custom(
    grid_rows: int = 50,
    grid_cols: int = 50,
    start_r: int = 0,
    start_c: int = 0,
    goal_r: int = -1,
    goal_c: int = -1,
    tier: str = "easy",
    moves: str = "8N",
    family: str = "random_field",
    time_limit: int = 30000,
    solver: str = "astar",
):
    """Generate a custom testcase and run a solver, streaming progress via SSE."""
    # Resolve default goal to bottom-right corner
    actual_goal_r = goal_r if goal_r >= 0 else grid_rows - 1
    actual_goal_c = goal_c if goal_c >= 0 else grid_cols - 1

    # Resolve solver path
    solver_map = {}
    if BASELINES_DIR.exists():
        for f in BASELINES_DIR.glob("*.py"):
            solver_map[f.stem] = f
    solver_path = solver_map.get(solver)
    if not solver_path:
        raise HTTPException(400, f"Unknown solver '{solver}'. Available: {list(solver_map.keys())}")

    async def _stream() -> AsyncGenerator[str, None]:
        stages = []
        tmp_dir = Path(tempfile.mkdtemp(prefix="rj_custom_"))

        try:
            # --- Stage 1: Generate testcase ---
            yield _sse_event("stage", {"name": "Generating Testcase", "status": "running", "index": 0})
            stage = {"name": "Generating Testcase", "status": "running", "output": ""}
            try:
                from robotjudge.generator import _FAMILY_MAP, _bfs_reachable, _ensure_solvable

                rng = _random_mod.Random(42)
                gen_fn = _FAMILY_MAP.get(family)
                if gen_fn is None:
                    raise ValueError(f"Unknown family '{family}'. Available: {list(_FAMILY_MAP.keys())}")

                # Generate grid
                params = {}
                if family == "random_field":
                    density = {"easy": 0.15, "medium": 0.22, "hard": 0.30}.get(tier, 0.15)
                    params = {"obstacle_density": [density, density]}
                elif family == "maze":
                    params = {"braid_factor": [0.05, 0.15]}
                elif family == "corridors":
                    params = {"corridor_width": [2, 3]}
                elif family == "rooms_doors":
                    params = {"rooms": [3, 6], "door_width": [1, 2]}
                elif family == "traps":
                    params = {"deadend_ratio": [0.2, 0.4]}
                elif family == "narrow_passages":
                    params = {"passage_width": [1, 2]}
                elif family == "high_density":
                    density = {"easy": 0.25, "medium": 0.30, "hard": 0.35}.get(tier, 0.30)
                    params = {"obstacle_density": [density, density]}

                grid = gen_fn(rng, grid_rows, grid_cols, params)

                # Clamp start/goal to grid
                s_r = max(0, min(actual_goal_r, grid_rows - 1))
                s_c = max(0, min(start_c, grid_cols - 1))
                g_r = max(0, min(actual_goal_r, grid_rows - 1))
                g_c = max(0, min(actual_goal_c, grid_cols - 1))
                s_r = max(0, min(start_r, grid_rows - 1))

                # Clear start and goal cells
                grid[s_r][s_c] = 0
                grid[g_r][g_c] = 0

                # Ensure solvable
                _ensure_solvable(rng, grid, (s_r, s_c), (g_r, g_c))

                case_id = f"custom_{uuid.uuid4().hex[:8]}"
                case_data = {
                    "version": "1.0",
                    "id": case_id,
                    "grid": grid,
                    "start": [s_r, s_c],
                    "goal": [g_r, g_c],
                    "moves": moves,
                    "meta": {"family": family, "tier": tier},
                }

                # Write testcase
                case_dir = tmp_dir / case_id
                case_dir.mkdir(parents=True, exist_ok=True)
                case_file = case_dir / "case.json"
                with open(case_file, "w", encoding="utf-8") as f:
                    json.dump(case_data, f, separators=(",", ":"))

                stage["output"] = (
                    f"Generated {grid_rows}×{grid_cols} grid ({family})\n"
                    f"Start: [{s_r}, {s_c}] → Goal: [{g_r}, {g_c}]\n"
                    f"Moves: {moves} | Tier: {tier}\n"
                    f"Case ID: {case_id}"
                )
                stage["status"] = "pass"
                stage["results"] = {
                    "grid_size": f"{grid_rows}×{grid_cols}",
                    "family": family,
                    "case_id": case_id,
                }
                # Include grid data for visualization
                stage["case_data"] = case_data
            except Exception as e:
                stage["output"] = str(e)
                stage["status"] = "error"
            stages.append(stage)
            yield _sse_event("stage_done", stage)

            if stage["status"] == "error":
                yield _sse_event("done", {"overall": "fail", "stages": stages})
                return

            # --- Stage 2: Schema Validation ---
            yield _sse_event("stage", {"name": "Schema Validation", "status": "running", "index": 1})
            stage2 = {"name": "Schema Validation", "status": "running", "output": ""}
            try:
                proc = _run_cmd([
                    "python", "-m", "robotjudge.cli", "validate",
                    str(case_file), "--type", "case",
                ], timeout=10)
                stage2["output"] = proc.stdout + proc.stderr
                stage2["status"] = "pass" if proc.returncode == 0 else "fail"
            except Exception as e:
                stage2["output"] = str(e)
                stage2["status"] = "error"
            stages.append(stage2)
            yield _sse_event("stage_done", stage2)

            # --- Stage 3: Running Solver ---
            yield _sse_event("stage", {"name": f"Running {solver.upper()} Solver", "status": "running", "index": 2})
            stage3 = {"name": f"Running {solver.upper()} Solver", "status": "running", "output": ""}
            try:
                import time
                out_path = tmp_dir / "path.json"
                t0 = time.perf_counter()
                proc = _run_cmd([
                    "python", str(solver_path),
                    "--case", str(case_file),
                    "--seed", "0",
                    "--out", str(out_path),
                ], timeout=time_limit / 1000)
                runtime_ms = int((time.perf_counter() - t0) * 1000)

                stage3["output"] = proc.stdout + proc.stderr
                if proc.returncode == 0 and out_path.exists():
                    with open(out_path, "r") as f:
                        path_data = json.load(f)
                    path_len = len(path_data.get("path", []))
                    stage3["status"] = "pass"
                    stage3["results"] = {
                        "status": "AC",
                        "path_length": path_len,
                        "runtime_ms": runtime_ms,
                        "solver": solver,
                    }
                    stage3["path_data"] = path_data
                    stage3["output"] += f"\nPath found: {path_len} cells in {runtime_ms}ms"
                else:
                    stage3["status"] = "fail"
                    stage3["results"] = {"status": "RTE", "runtime_ms": runtime_ms}
            except subprocess.TimeoutExpired:
                stage3["output"] = f"Solver timed out after {time_limit}ms"
                stage3["status"] = "fail"
                stage3["results"] = {"status": "TLE", "runtime_ms": time_limit}
            except Exception as e:
                stage3["output"] = str(e)
                stage3["status"] = "error"
            stages.append(stage3)
            yield _sse_event("stage_done", stage3)

            # --- Stage 4: Path Validation ---
            yield _sse_event("stage", {"name": "Path Validation", "status": "running", "index": 3})
            stage4 = {"name": "Path Validation", "status": "running", "output": ""}
            try:
                out_path = tmp_dir / "path.json"
                if out_path.exists():
                    proc = _run_cmd([
                        "python", "-m", "robotjudge.cli", "validate",
                        str(out_path), "--type", "path",
                    ], timeout=10)
                    stage4["output"] = proc.stdout + proc.stderr
                    stage4["status"] = "pass" if proc.returncode == 0 else "fail"
                else:
                    stage4["output"] = "No path output file found"
                    stage4["status"] = "skip"
            except Exception as e:
                stage4["output"] = str(e)
                stage4["status"] = "error"
            stages.append(stage4)
            yield _sse_event("stage_done", stage4)

        finally:
            # Cleanup temp dir
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

        # Final event
        overall = "pass" if all(s["status"] in ("pass", "skip") for s in stages) else "fail"
        yield _sse_event("done", {
            "overall": overall,
            "stages": stages,
            "timestamp": datetime.datetime.now().isoformat(),
        })

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/api/ci/run-custom-upload")
async def api_ci_run_custom_upload(
    solver_file: UploadFile = File(...),
    grid_rows: int = Form(50),
    grid_cols: int = Form(50),
    start_r: int = Form(0),
    start_c: int = Form(0),
    goal_r: int = Form(-1),
    goal_c: int = Form(-1),
    tier: str = Form("easy"),
    moves: str = Form("8N"),
    family: str = Form("random_field"),
    time_limit: int = Form(30000),
):
    """Run a custom testcase with an uploaded solver, streaming progress via SSE."""
    actual_goal_r = goal_r if goal_r >= 0 else grid_rows - 1
    actual_goal_c = goal_c if goal_c >= 0 else grid_cols - 1

    # Save uploaded solver to temp location
    upload_tmp = Path(tempfile.mkdtemp(prefix="rj_upload_"))
    solver_path = upload_tmp / solver_file.filename
    content = await solver_file.read()
    with open(solver_path, "wb") as f:
        f.write(content)

    solver_name = solver_file.filename

    async def _stream() -> AsyncGenerator[str, None]:
        stages = []
        tmp_dir = Path(tempfile.mkdtemp(prefix="rj_custom_"))

        try:
            # --- Stage 1: Generate testcase ---
            yield _sse_event("stage", {"name": "Generating Testcase", "status": "running", "index": 0})
            stage = {"name": "Generating Testcase", "status": "running", "output": ""}
            try:
                from robotjudge.generator import _FAMILY_MAP, _bfs_reachable, _ensure_solvable

                rng = _random_mod.Random(42)
                gen_fn = _FAMILY_MAP.get(family)
                if gen_fn is None:
                    raise ValueError(f"Unknown family '{family}'. Available: {list(_FAMILY_MAP.keys())}")

                params = {}
                if family == "random_field":
                    density = {"easy": 0.15, "medium": 0.22, "hard": 0.30}.get(tier, 0.15)
                    params = {"obstacle_density": [density, density]}
                elif family == "maze":
                    params = {"braid_factor": [0.05, 0.15]}
                elif family == "corridors":
                    params = {"corridor_width": [2, 3]}
                elif family == "rooms_doors":
                    params = {"rooms": [3, 6], "door_width": [1, 2]}
                elif family == "traps":
                    params = {"deadend_ratio": [0.2, 0.4]}
                elif family == "narrow_passages":
                    params = {"passage_width": [1, 2]}
                elif family == "high_density":
                    density = {"easy": 0.25, "medium": 0.30, "hard": 0.35}.get(tier, 0.30)
                    params = {"obstacle_density": [density, density]}

                grid = gen_fn(rng, grid_rows, grid_cols, params)

                s_r = max(0, min(actual_goal_r, grid_rows - 1))
                s_c = max(0, min(start_c, grid_cols - 1))
                g_r = max(0, min(actual_goal_r, grid_rows - 1))
                g_c = max(0, min(actual_goal_c, grid_cols - 1))
                s_r = start_r
                s_c = start_c
                grid[s_r][s_c] = 0
                grid[g_r][g_c] = 0
                _ensure_solvable(rng, grid, (s_r, s_c), (g_r, g_c))

                case_id = f"custom_{uuid.uuid4().hex[:8]}"
                case_data = {
                    "version": "1.0",
                    "id": case_id,
                    "grid": grid,
                    "start": [s_r, s_c],
                    "goal": [g_r, g_c],
                    "moves": moves,
                    "meta": {"family": family, "tier": tier},
                }

                case_dir = tmp_dir / case_id
                case_dir.mkdir(parents=True, exist_ok=True)
                case_file = case_dir / "case.json"
                with open(case_file, "w", encoding="utf-8") as f:
                    json.dump(case_data, f, separators=(",", ":"))

                stage["output"] = (
                    f"Generated {grid_rows}×{grid_cols} grid ({family})\n"
                    f"Start: [{s_r}, {s_c}] → Goal: [{g_r}, {g_c}]\n"
                    f"Moves: {moves} | Tier: {tier}\n"
                    f"Case ID: {case_id}"
                )
                stage["status"] = "pass"
                stage["results"] = {
                    "grid_size": f"{grid_rows}×{grid_cols}",
                    "family": family,
                    "case_id": case_id,
                }
                stage["case_data"] = case_data
            except Exception as e:
                stage["output"] = str(e)
                stage["status"] = "error"
            stages.append(stage)
            yield _sse_event("stage_done", stage)

            if stage["status"] == "error":
                yield _sse_event("done", {"overall": "fail", "stages": stages})
                return

            # --- Stage 2: Schema Validation ---
            yield _sse_event("stage", {"name": "Schema Validation", "status": "running", "index": 1})
            stage2 = {"name": "Schema Validation", "status": "running", "output": ""}
            try:
                proc = _run_cmd([
                    "python", "-m", "robotjudge.cli", "validate",
                    str(case_file), "--type", "case",
                ], timeout=10)
                stage2["output"] = proc.stdout + proc.stderr
                stage2["status"] = "pass" if proc.returncode == 0 else "fail"
            except Exception as e:
                stage2["output"] = str(e)
                stage2["status"] = "error"
            stages.append(stage2)
            yield _sse_event("stage_done", stage2)

            # --- Stage 3: Running Uploaded Solver ---
            yield _sse_event("stage", {"name": f"Running {solver_name}", "status": "running", "index": 2})
            stage3 = {"name": f"Running {solver_name}", "status": "running", "output": ""}
            try:
                import time
                out_path = tmp_dir / "path.json"
                t0 = time.perf_counter()
                proc = _run_cmd([
                    "python", str(solver_path),
                    "--case", str(case_file),
                    "--seed", "0",
                    "--out", str(out_path),
                ], timeout=time_limit / 1000)
                runtime_ms = int((time.perf_counter() - t0) * 1000)

                stage3["output"] = proc.stdout + proc.stderr
                if proc.returncode == 0 and out_path.exists():
                    with open(out_path, "r") as f:
                        path_data = json.load(f)
                    path_len = len(path_data.get("path", []))
                    stage3["status"] = "pass"
                    stage3["results"] = {
                        "status": "AC",
                        "path_length": path_len,
                        "runtime_ms": runtime_ms,
                        "solver": solver_name,
                    }
                    stage3["path_data"] = path_data
                    stage3["output"] += f"\nPath found: {path_len} cells in {runtime_ms}ms"
                else:
                    stage3["status"] = "fail"
                    stage3["results"] = {"status": "RTE", "runtime_ms": runtime_ms}
            except subprocess.TimeoutExpired:
                stage3["output"] = f"Solver timed out after {time_limit}ms"
                stage3["status"] = "fail"
                stage3["results"] = {"status": "TLE", "runtime_ms": time_limit}
            except Exception as e:
                stage3["output"] = str(e)
                stage3["status"] = "error"
            stages.append(stage3)
            yield _sse_event("stage_done", stage3)

            # --- Stage 4: Path Validation ---
            yield _sse_event("stage", {"name": "Path Validation", "status": "running", "index": 3})
            stage4 = {"name": "Path Validation", "status": "running", "output": ""}
            try:
                out_path = tmp_dir / "path.json"
                if out_path.exists():
                    proc = _run_cmd([
                        "python", "-m", "robotjudge.cli", "validate",
                        str(out_path), "--type", "path",
                    ], timeout=10)
                    stage4["output"] = proc.stdout + proc.stderr
                    stage4["status"] = "pass" if proc.returncode == 0 else "fail"
                else:
                    stage4["output"] = "No path output file found"
                    stage4["status"] = "skip"
            except Exception as e:
                stage4["output"] = str(e)
                stage4["status"] = "error"
            stages.append(stage4)
            yield _sse_event("stage_done", stage4)

        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                shutil.rmtree(upload_tmp, ignore_errors=True)
            except Exception:
                pass

        overall = "pass" if all(s["status"] in ("pass", "skip") for s in stages) else "fail"
        yield _sse_event("done", {
            "overall": overall,
            "stages": stages,
            "timestamp": datetime.datetime.now().isoformat(),
        })

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.get("/api/ci/quick-check")
async def api_ci_quick_check():
    """Quick CI check — unit tests only (fast)."""
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=30,
        )
        lines = proc.stdout.strip().split("\n")
        # Parse pytest output
        passed = sum(1 for l in lines if " PASSED" in l)
        failed = sum(1 for l in lines if " FAILED" in l)
        total = passed + failed

        return {
            "status": "pass" if proc.returncode == 0 else "fail",
            "passed": passed,
            "failed": failed,
            "total": total,
            "output": proc.stdout + proc.stderr,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# API — Submission
# ---------------------------------------------------------------------------

# In-memory job tracker (also persisted to DB for durability)
_jobs: dict[str, dict] = {}


@app.post("/api/submit")
async def api_submit(
    solver: UploadFile = File(...),
    seeds: str = Form("0..4"),
    time_limit: int = Form(30000),
    quick_run: bool = Form(False),
):
    """Accept a solver file and queue a judge run."""
    job_id = uuid.uuid4().hex[:8]

    # Save uploaded file to disk (needed for subprocess execution)
    upload_dir = SUBMISSIONS_DIR / f"upload_{job_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    solver_path = upload_dir / solver.filename
    content = await solver.read()
    with open(solver_path, "wb") as f:
        f.write(content)

    # Also save solver source to DB
    db = get_db()
    try:
        db.add(Solver(
            name=f"{solver.filename.replace('.py','')}_{job_id}",
            filename=solver.filename,
            solver_type="uploaded",
            source_code=content.decode("utf-8", errors="replace"),
        ))
        db.commit()
    finally:
        db.close()

    if quick_run:
        seeds = "0"

    job_data = {
        "id": job_id,
        "status": "queued",
        "solver_name": solver.filename,
        "seeds": seeds,
        "time_limit": time_limit,
        "progress": 0,
        "total": 0,
        "result_name": None,
        "error": None,
    }
    _jobs[job_id] = {**job_data, "solver": str(solver_path)}

    # Persist to DB
    db = get_db()
    try:
        upsert_job(db, job_data)
    finally:
        db.close()

    asyncio.create_task(_run_judge(job_id))
    return {"job_id": job_id}


def _parse_seeds_count(seeds_str: str) -> int:
    if ".." in seeds_str:
        parts = seeds_str.split("..")
        return int(parts[1]) - int(parts[0]) + 1
    return len(seeds_str.split(","))


async def _run_judge(job_id: str):
    """Run the judge pipeline asynchronously."""
    job = _jobs[job_id]
    job["status"] = "running"

    report_dir = REPORTS_DIR / f"submission_{job_id}"
    logs_dir = report_dir / "logs"
    
    # Calculate total runs
    try:
        case_count = len(list(TESTCASES_DIR.rglob("case.json")))
        seed_count = _parse_seeds_count(job["seeds"])
        job["total"] = case_count * seed_count
    except Exception:
        job["total"] = 0

    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "robotjudge.cli", "run",
            "--suite", str(TESTCASES_DIR),
            "--submission", job["solver"],
            "--seeds", job["seeds"],
            "--report-dir", str(report_dir),
            "--time-limit", str(job["time_limit"]),
            cwd=str(PROJECT_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def poll_progress():
            while proc.returncode is None:
                if logs_dir.exists():
                    count = len(list(logs_dir.glob("*_path.json")))
                    job["progress"] = count
                await asyncio.sleep(1)
                
        poller = asyncio.create_task(poll_progress())
        stdout, stderr = await proc.communicate()
        poller.cancel()

        if proc.returncode == 0:
            job["status"] = "done"
            job["result_name"] = f"submission_{job_id}"
        else:
            if (report_dir / "results.json").exists():
                job["status"] = "done"
                job["result_name"] = f"submission_{job_id}"
            else:
                job["status"] = "error"
                job["error"] = stderr.decode("utf-8", errors="replace")[-500:]

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)

    # Update DB
    db = get_db()
    try:
        upsert_job(db, {"id": job_id, "status": job["status"],
                        "result_name": job.get("result_name"),
                        "error": job.get("error")})
    finally:
        db.close()


@app.get("/api/jobs/{job_id}")
async def api_job_status(job_id: str):
    """Poll job status."""
    if job_id in _jobs:
        return _jobs[job_id]
    db = get_db()
    try:
        data = get_job(db, job_id)
        if not data:
            raise HTTPException(404, f"Job '{job_id}' not found")
        return data
    finally:
        db.close()


@app.get("/api/jobs")
async def api_jobs():
    """List all jobs."""
    db = get_db()
    try:
        return get_all_jobs(db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"RobotJudge Web UI: http://localhost:{port}")
    print(f"Project root: {PROJECT_ROOT}")
    uvicorn.run(app, host="0.0.0.0", port=port)
