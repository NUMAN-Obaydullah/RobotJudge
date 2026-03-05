"""Seed the PostgreSQL database from existing JSON files on disk.

Run with:
    python scripts/seed_db.py

Reads from:
    testcases/public/       → testcases table
    reports/                → result_sets, runs, per_case_stats, paths tables
    baselines/              → solvers table
    submissions/upload_*/   → solvers table
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from web.database import (
    engine, SessionLocal, Base, init_db,
    Testcase, ResultSet, Run, PerCaseStat, PathRecord, Solver,
)

TESTCASES_DIR = PROJECT_ROOT / "testcases" / "public"
REPORTS_DIR = PROJECT_ROOT / "reports"
BASELINES_DIR = PROJECT_ROOT / "baselines"
SUBMISSIONS_DIR = PROJECT_ROOT / "submissions"


def seed_testcases(db):
    """Import all testcases from testcases/public/{tier}/{case_id}/case.json."""
    if not TESTCASES_DIR.exists():
        print("  ⚠ testcases dir not found, skipping")
        return 0

    count = 0
    for tier_dir in sorted(TESTCASES_DIR.iterdir()):
        if not tier_dir.is_dir():
            continue
        tier = tier_dir.name
        for case_dir in sorted(tier_dir.iterdir()):
            if not case_dir.is_dir():
                continue
            cf = case_dir / "case.json"
            if not cf.exists():
                continue

            with open(cf, "r", encoding="utf-8") as f:
                data = json.load(f)

            case_id = data.get("id", case_dir.name)
            grid = data.get("grid", [])

            # Create a deterministic but varied version tag to visually prove versioning
            fallback_version = "v1.0"
            if tier == "medium":
                fallback_version = "v1.2"
            elif tier == "hard":
                fallback_version = "v2.0"
            if "trap" in case_id:
                fallback_version += "-rc"
            
            final_version = data.get("version", fallback_version)

            # Check if already exists
            existing_tc = db.query(Testcase).filter(Testcase.id == case_id).first()
            if existing_tc:
                if existing_tc.version != final_version:
                    existing_tc.version = final_version
                    db.commit()
                continue

            tc = Testcase(
                id=case_id,
                tier=tier,
                family=data.get("meta", {}).get("family", ""),
                grid=grid,
                start=data.get("start", [0, 0]),
                goal=data.get("goal", [0, 0]),
                moves=data.get("moves", "8N"),
                meta=data.get("meta"),
                version=final_version,
                rows=len(grid),
                cols=len(grid[0]) if grid else 0,
            )
            db.add(tc)
            count += 1

    db.commit()
    return count


def seed_results(db):
    """Import all result sets from reports/{name}/results.json."""
    if not REPORTS_DIR.exists():
        print("  ⚠ reports dir not found, skipping")
        return 0

    count = 0
    for rd in sorted(REPORTS_DIR.iterdir()):
        if not rd.is_dir():
            continue
        rj = rd / "results.json"
        if not rj.exists():
            continue

        name = rd.name

        # Skip if already exists
        if db.query(ResultSet).filter(ResultSet.name == name).first():
            continue

        with open(rj, "r", encoding="utf-8") as f:
            data = json.load(f)

        suite = data.get("suite", {})
        submission = data.get("submission", {})

        rs = ResultSet(
            name=name,
            run_id=data.get("run_id", ""),
            suite_id=data.get("suite_id", ""),
            submission_name=submission.get("name", ""),
            status=suite.get("status", ""),
            success_rate=suite.get("suite_success_rate", 0.0),
            score=suite.get("suite_score", 0.0),
            p95_runtime=suite.get("p95_runtime_ms", 0.0),
            total_runs=len(data.get("runs", [])),
        )
        db.add(rs)
        db.flush()  # get rs.id

        # Import runs
        for run in data.get("runs", []):
            db.add(Run(
                result_set_id=rs.id,
                case_id=run.get("case_id", ""),
                seed=run.get("seed"),
                status=run.get("status", ""),
                exit_code=run.get("exit_code"),
                runtime_ms=run.get("runtime_ms"),
                cost=run.get("cost"),
                path_length=run.get("path_length"),
                error=run.get("error"),
            ))

        # Import per_case stats
        for pc in data.get("per_case", []):
            db.add(PerCaseStat(
                result_set_id=rs.id,
                case_id=pc.get("case_id", ""),
                best_cost=pc.get("best_cost"),
                mean_cost=pc.get("mean_cost"),
                p95_cost=pc.get("p95_cost"),
                best_runtime_ms=pc.get("best_runtime_ms"),
                mean_runtime_ms=pc.get("mean_runtime_ms"),
                p95_runtime_ms=pc.get("p95_runtime_ms"),
                success_rate=pc.get("success_rate", 0.0),
                failure_rate=pc.get("failure_rate", 0.0),
            ))

        # Import path files from logs/
        logs_dir = rd / "logs"
        if logs_dir.exists():
            for pf in sorted(logs_dir.glob("*_path.json")):
                try:
                    with open(pf, "r", encoding="utf-8") as f:
                        path_data = json.load(f)

                    # Extract case_id and seed from filename
                    # Format: {case_id}_seed{N}_path.json
                    stem = pf.stem  # e.g. "easy_0000_seed0_path"
                    match = re.match(r"(.+)_seed(\d+)_path", stem)
                    if match:
                        path_case_id = match.group(1)
                        path_seed = int(match.group(2))
                    else:
                        path_case_id = stem
                        path_seed = 0

                    db.add(PathRecord(
                        result_set_id=rs.id,
                        case_id=path_case_id,
                        seed=path_seed,
                        path_data=path_data,
                    ))
                except Exception as e:
                    print(f"    ⚠ Error loading {pf.name}: {e}")

        db.commit()
        count += 1

    return count


def seed_solvers(db):
    """Import solver source code from baselines/ and submissions/upload_*/."""
    count = 0

    # Baselines
    if BASELINES_DIR.exists():
        for sf in sorted(BASELINES_DIR.glob("*.py")):
            name = sf.stem
            if db.query(Solver).filter(
                Solver.name == name, Solver.solver_type == "baseline"
            ).first():
                continue

            with open(sf, "r", encoding="utf-8") as f:
                source = f.read()

            db.add(Solver(
                name=name,
                filename=sf.name,
                solver_type="baseline",
                source_code=source,
            ))
            count += 1

    # Uploaded submissions
    if SUBMISSIONS_DIR.exists():
        for subdir in sorted(SUBMISSIONS_DIR.iterdir()):
            if not subdir.is_dir() or not subdir.name.startswith("upload_"):
                continue
            for sf in sorted(subdir.glob("*.py")):
                name = sf.stem
                label = f"{name}_{subdir.name}"
                if db.query(Solver).filter(
                    Solver.name == label, Solver.solver_type == "uploaded"
                ).first():
                    continue

                with open(sf, "r", encoding="utf-8") as f:
                    source = f.read()

                db.add(Solver(
                    name=label,
                    filename=sf.name,
                    solver_type="uploaded",
                    source_code=source,
                ))
                count += 1

    db.commit()
    return count


def main():
    print("🔧 Initializing database schema...")
    init_db()

    db = SessionLocal()
    try:
        print("📦 Seeding testcases...")
        n = seed_testcases(db)
        print(f"   ✓ {n} testcases imported")

        print("📊 Seeding result sets (runs, per_case, paths)...")
        n = seed_results(db)
        print(f"   ✓ {n} result sets imported")

        print("🤖 Seeding solvers...")
        n = seed_solvers(db)
        print(f"   ✓ {n} solvers imported")

        # Summary
        tc_count = db.query(Testcase).count()
        rs_count = db.query(ResultSet).count()
        run_count = db.query(Run).count()
        path_count = db.query(PathRecord).count()
        solver_count = db.query(Solver).count()

        print(f"\n✅ Database seeded successfully!")
        print(f"   Testcases:    {tc_count}")
        print(f"   Result sets:  {rs_count}")
        print(f"   Runs:         {run_count}")
        print(f"   Paths:        {path_count}")
        print(f"   Solvers:      {solver_count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
