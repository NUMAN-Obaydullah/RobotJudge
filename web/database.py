"""RobotJudge-CI Database Layer — SQLAlchemy + PostgreSQL.

Provides the ORM models, engine/session factory, and CRUD helpers
used by the web server.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column, Integer, Float, String, Text, Boolean, DateTime,
    ForeignKey, JSON, create_engine, Index,
)
from sqlalchemy.orm import (
    DeclarativeBase, Session, relationship, sessionmaker,
)

# ---------------------------------------------------------------------------
# Engine / Session
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://rj:rj@localhost:5432/robotjudge",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Session:
    """Return a new DB session (caller must close)."""
    return SessionLocal()


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Testcase(Base):
    __tablename__ = "testcases"

    id = Column(String, primary_key=True)              # e.g. "easy_0000"
    tier = Column(String, nullable=False, index=True)   # easy / medium / hard
    family = Column(String, nullable=True)
    grid = Column(JSON, nullable=False)                 # 2D list
    start = Column(JSON, nullable=False)                # [r, c]
    goal = Column(JSON, nullable=False)                 # [r, c]
    moves = Column(String, nullable=False, default="8N")
    meta = Column(JSON, nullable=True)
    version = Column(String, default="1.0")
    rows = Column(Integer, nullable=True)
    cols = Column(Integer, nullable=True)


class ResultSet(Base):
    __tablename__ = "result_sets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    run_id = Column(String, nullable=True)
    suite_id = Column(String, nullable=True)
    submission_name = Column(String, nullable=True)
    status = Column(String, nullable=True)
    success_rate = Column(Float, default=0.0)
    score = Column(Float, default=0.0)
    p95_runtime = Column(Float, default=0.0)
    total_runs = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # relationships
    runs = relationship("Run", back_populates="result_set", cascade="all,delete")
    per_case_stats = relationship("PerCaseStat", back_populates="result_set", cascade="all,delete")
    paths = relationship("PathRecord", back_populates="result_set", cascade="all,delete")


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_set_id = Column(Integer, ForeignKey("result_sets.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String, nullable=False, index=True)
    seed = Column(Integer, nullable=True)
    status = Column(String, nullable=True)           # AC, WA, TLE, RTE …
    exit_code = Column(Integer, nullable=True)
    runtime_ms = Column(Float, nullable=True)
    cost = Column(Float, nullable=True)
    path_length = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)

    result_set = relationship("ResultSet", back_populates="runs")


class PerCaseStat(Base):
    __tablename__ = "per_case_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_set_id = Column(Integer, ForeignKey("result_sets.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String, nullable=False, index=True)
    best_cost = Column(Float, nullable=True)
    mean_cost = Column(Float, nullable=True)
    p95_cost = Column(Float, nullable=True)
    best_runtime_ms = Column(Float, nullable=True)
    mean_runtime_ms = Column(Float, nullable=True)
    p95_runtime_ms = Column(Float, nullable=True)
    success_rate = Column(Float, default=0.0)
    failure_rate = Column(Float, default=0.0)

    result_set = relationship("ResultSet", back_populates="per_case_stats")


class PathRecord(Base):
    __tablename__ = "paths"

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_set_id = Column(Integer, ForeignKey("result_sets.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String, nullable=False, index=True)
    seed = Column(Integer, nullable=True)
    path_data = Column(JSON, nullable=False)          # full path JSON

    result_set = relationship("ResultSet", back_populates="paths")


class Solver(Base):
    __tablename__ = "solvers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, index=True)  # filename without ext
    filename = Column(String, nullable=False)           # full filename
    solver_type = Column(String, nullable=False)        # "baseline" or "uploaded"
    source_code = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    status = Column(String, default="queued")
    solver_name = Column(String, nullable=True)
    seeds = Column(String, nullable=True)
    time_limit = Column(Integer, nullable=True)
    progress = Column(Integer, default=0)
    total = Column(Integer, default=0)
    result_name = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------
def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

# -- Testcases --
def get_all_testcases(db: Session, *, include_grid: bool = False) -> list[dict]:
    """List testcases. If include_grid=False, omit the large grid column."""
    if include_grid:
        rows = db.query(Testcase).order_by(Testcase.id).all()
    else:
        rows = db.query(
            Testcase.id, Testcase.tier, Testcase.family,
            Testcase.start, Testcase.goal, Testcase.moves,
            Testcase.rows, Testcase.cols, Testcase.meta,
        ).order_by(Testcase.id).all()

    results = []
    for r in rows:
        if include_grid:
            results.append(_testcase_to_dict(r))
        else:
            results.append({
                "id": r.id, "tier": r.tier, "family": r.family,
                "start": r.start, "goal": r.goal, "moves": r.moves,
                "rows": r.rows, "cols": r.cols, "meta": r.meta,
            })
    return results


def get_testcase(db: Session, case_id: str) -> dict | None:
    tc = db.query(Testcase).filter(Testcase.id == case_id).first()
    return _testcase_to_dict(tc) if tc else None


def _testcase_to_dict(tc: Testcase) -> dict:
    return {
        "id": tc.id, "version": tc.version, "tier": tc.tier,
        "family": tc.family, "grid": tc.grid,
        "start": tc.start, "goal": tc.goal, "moves": tc.moves,
        "rows": tc.rows, "cols": tc.cols, "meta": tc.meta,
    }


# -- Result Sets --
def get_all_result_sets(db: Session) -> list[dict]:
    rows = db.query(ResultSet).order_by(ResultSet.name).all()
    return [{
        "name": r.name,
        "run_id": r.run_id,
        "suite_id": r.suite_id,
        "submission": r.submission_name,
        "status": r.status,
        "success_rate": r.success_rate,
        "score": r.score,
        "p95_runtime": r.p95_runtime,
        "total_runs": r.total_runs,
    } for r in rows]


def get_result_set_detail(db: Session, name: str) -> dict | None:
    rs = db.query(ResultSet).filter(ResultSet.name == name).first()
    if not rs:
        return None
    runs = [{
        "case_id": r.case_id, "seed": r.seed, "status": r.status,
        "exit_code": r.exit_code, "runtime_ms": r.runtime_ms,
        "cost": r.cost, "path_length": r.path_length, "error": r.error,
    } for r in rs.runs]

    per_case = [{
        "case_id": p.case_id, "best_cost": p.best_cost,
        "mean_cost": p.mean_cost, "p95_cost": p.p95_cost,
        "best_runtime_ms": p.best_runtime_ms,
        "mean_runtime_ms": p.mean_runtime_ms,
        "p95_runtime_ms": p.p95_runtime_ms,
        "success_rate": p.success_rate, "failure_rate": p.failure_rate,
    } for p in rs.per_case_stats]

    return {
        "run_id": rs.run_id,
        "suite_id": rs.suite_id,
        "submission": {"name": rs.submission_name},
        "suite": {
            "status": rs.status,
            "suite_success_rate": rs.success_rate,
            "suite_score": rs.score,
            "p95_runtime_ms": rs.p95_runtime,
        },
        "runs": runs,
        "per_case": per_case,
    }


# -- Case Results (runs + paths for a specific case from a result set) --
def get_case_results(db: Session, result_name: str, case_id: str) -> dict | None:
    rs = db.query(ResultSet).filter(ResultSet.name == result_name).first()
    if not rs:
        return None

    runs = [{
        "case_id": r.case_id, "seed": r.seed, "status": r.status,
        "exit_code": r.exit_code, "runtime_ms": r.runtime_ms,
        "cost": r.cost, "path_length": r.path_length, "error": r.error,
    } for r in db.query(Run).filter(
        Run.result_set_id == rs.id, Run.case_id == case_id
    ).all()]

    per_case_rows = db.query(PerCaseStat).filter(
        PerCaseStat.result_set_id == rs.id, PerCaseStat.case_id == case_id
    ).all()
    per_case = None
    if per_case_rows:
        p = per_case_rows[0]
        per_case = {
            "case_id": p.case_id, "best_cost": p.best_cost,
            "mean_cost": p.mean_cost, "p95_cost": p.p95_cost,
            "best_runtime_ms": p.best_runtime_ms,
            "mean_runtime_ms": p.mean_runtime_ms,
            "p95_runtime_ms": p.p95_runtime_ms,
            "success_rate": p.success_rate, "failure_rate": p.failure_rate,
        }

    paths = [pr.path_data for pr in db.query(PathRecord).filter(
        PathRecord.result_set_id == rs.id, PathRecord.case_id == case_id
    ).order_by(PathRecord.seed).all()]

    return {"runs": runs, "per_case": per_case, "paths": paths}


# -- Solvers --
def get_all_solvers(db: Session) -> list[dict]:
    rows = db.query(Solver).order_by(Solver.solver_type, Solver.name).all()
    return [{
        "name": s.name, "filename": s.filename,
        "type": s.solver_type,
    } for s in rows]


def get_solver_code(db: Session, solver_type: str, solver_name: str) -> str | None:
    s = db.query(Solver).filter(
        Solver.solver_type == solver_type, Solver.name == solver_name
    ).first()
    return s.source_code if s else None


# -- Jobs --
def upsert_job(db: Session, job: dict):
    existing = db.query(Job).filter(Job.id == job["id"]).first()
    if existing:
        for k, v in job.items():
            setattr(existing, k, v)
    else:
        db.add(Job(**job))
    db.commit()


def get_job(db: Session, job_id: str) -> dict | None:
    j = db.query(Job).filter(Job.id == job_id).first()
    if not j:
        return None
    return {
        "id": j.id, "status": j.status, "solver_name": j.solver_name,
        "seeds": j.seeds, "time_limit": j.time_limit,
        "progress": j.progress, "total": j.total,
        "result_name": j.result_name, "error": j.error,
    }


def get_all_jobs(db: Session) -> list[dict]:
    rows = db.query(Job).order_by(Job.created_at.desc()).all()
    return [{
        "id": j.id, "status": j.status, "solver_name": j.solver_name,
        "progress": j.progress, "total": j.total,
        "result_name": j.result_name, "error": j.error,
    } for j in rows]
