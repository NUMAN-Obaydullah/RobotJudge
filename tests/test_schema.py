"""Tests for RobotJudge-CI: schema validation, generator, grader, and end-to-end."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest

from robotjudge.schema import (
    validate_case,
    validate_case_schema,
    validate_path,
    validate_path_schema,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal valid data
# ---------------------------------------------------------------------------

def _minimal_case() -> dict:
    return {
        "version": "1.0",
        "id": "test_001",
        "grid": [[0, 0, 0], [0, 1, 0], [0, 0, 0]],
        "start": [0, 0],
        "goal": [2, 2],
        "moves": "8N",
    }


def _minimal_path(case_id: str = "test_001", seed: int = 0) -> dict:
    return {
        "version": "1.0",
        "case_id": case_id,
        "seed": seed,
        "path": [[0, 0], [1, 0], [2, 1], [2, 2]],
    }


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

class TestCaseSchema:
    def test_valid(self):
        assert validate_case_schema(_minimal_case()) == []

    def test_missing_version(self):
        c = _minimal_case()
        del c["version"]
        assert len(validate_case_schema(c)) > 0

    def test_bad_moves(self):
        c = _minimal_case()
        c["moves"] = "6N"
        assert len(validate_case_schema(c)) > 0

    def test_bad_grid_value(self):
        c = _minimal_case()
        c["grid"] = [[0, 2, 0]]
        assert len(validate_case_schema(c)) > 0


class TestPathSchema:
    def test_valid_cells(self):
        assert validate_path_schema(_minimal_path()) == []

    def test_valid_actions(self):
        p = {
            "version": "1.0",
            "case_id": "t",
            "seed": 0,
            "path": ["D", "D", "R", "R"],
        }
        assert validate_path_schema(p) == []

    def test_missing_path(self):
        p = {"version": "1.0", "case_id": "t", "seed": 0}
        assert len(validate_path_schema(p)) > 0


# ---------------------------------------------------------------------------
# Semantic validation tests
# ---------------------------------------------------------------------------

class TestCaseSemantic:
    def test_valid(self):
        assert validate_case(_minimal_case()) == []

    def test_start_on_obstacle(self):
        c = _minimal_case()
        c["start"] = [1, 1]  # obstacle
        errors = validate_case(c)
        assert any("obstacle" in e for e in errors)

    def test_start_out_of_bounds(self):
        c = _minimal_case()
        c["start"] = [10, 10]
        errors = validate_case(c)
        assert any("out of bounds" in e for e in errors)


class TestPathSemantic:
    def test_valid_path(self):
        case = _minimal_case()
        path = _minimal_path()
        valid, viols, metrics = validate_path(path, case)
        assert valid
        assert viols == []
        assert metrics["reached_goal"]
        assert not metrics["collision"]
        assert metrics["path_length"] > 0

    def test_wrong_start(self):
        case = _minimal_case()
        path = _minimal_path()
        path["path"][0] = [1, 0]  # doesn't start at [0,0]
        valid, viols, _ = validate_path(path, case)
        assert not valid
        assert any("starts at" in v for v in viols)

    def test_wrong_goal(self):
        case = _minimal_case()
        path = _minimal_path()
        path["path"][-1] = [1, 0]
        valid, viols, _ = validate_path(path, case)
        assert not valid
        assert any("ends at" in v for v in viols)

    def test_obstacle_collision(self):
        case = _minimal_case()
        path = _minimal_path()
        path["path"] = [[0, 0], [1, 1], [2, 2]]  # (1,1) is obstacle
        valid, viols, metrics = validate_path(path, case)
        assert not valid
        assert metrics["collision"]

    def test_illegal_move_4n(self):
        case = _minimal_case()
        case["moves"] = "4N"
        path = _minimal_path()
        path["path"] = [[0, 0], [1, 1]]  # diagonal, illegal under 4N
        valid, viols, _ = validate_path(path, case)
        assert not valid
        assert any("illegal" in v for v in viols)

    def test_action_list_mode(self):
        case = _minimal_case()
        case["moves"] = "4N"
        path = {
            "version": "1.0",
            "case_id": "test_001",
            "seed": 0,
            "path": ["D", "D", "R", "R"],
        }
        valid, viols, metrics = validate_path(path, case)
        assert valid
        assert metrics["reached_goal"]


# ---------------------------------------------------------------------------
# Generator tests
# ---------------------------------------------------------------------------

class TestGenerator:
    def test_generate_suite(self, tmp_path: Path):
        from robotjudge.generator import generate_suite

        # Use the real config
        config = Path(__file__).parent.parent / "configs" / "public_suite.yaml"
        if not config.exists():
            pytest.skip("No config file found")

        cases = generate_suite(config, tmp_path / "out", master_seed=42)
        assert len(cases) > 0

        # Verify every generated case validates
        for cp in cases[:5]:  # check first 5 for speed
            with open(cp, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            errors = validate_case(data)
            assert errors == [], f"Case {cp} invalid: {errors}"

    def test_determinism(self, tmp_path: Path):
        from robotjudge.generator import generate_suite

        config = Path(__file__).parent.parent / "configs" / "public_suite.yaml"
        if not config.exists():
            pytest.skip("No config file found")

        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        cases1 = generate_suite(config, out1, master_seed=42)
        cases2 = generate_suite(config, out2, master_seed=42)
        assert len(cases1) == len(cases2)

        for c1, c2 in zip(cases1[:5], cases2[:5]):
            d1 = json.loads(c1.read_text(encoding="utf-8"))
            d2 = json.loads(c2.read_text(encoding="utf-8"))
            assert d1 == d2, f"Non-deterministic: {c1.name}"


# ---------------------------------------------------------------------------
# Grader tests
# ---------------------------------------------------------------------------

class TestGrader:
    def test_aggregate_case_all_ac(self):
        from robotjudge.grader import aggregate_case

        runs = [
            {"case_id": "t", "seed": i, "status": "AC", "cost": 10.0 + i,
             "runtime_ms": 50 + i, "path_length": 10.0 + i}
            for i in range(5)
        ]
        agg = aggregate_case(runs)
        assert agg["success_rate"] == 1.0
        assert agg["failure_rate"] == 0.0
        assert agg["best_cost"] == 10.0

    def test_aggregate_case_partial_failure(self):
        from robotjudge.grader import aggregate_case

        runs = [
            {"case_id": "t", "seed": 0, "status": "AC", "cost": 10.0, "runtime_ms": 50, "path_length": 10.0},
            {"case_id": "t", "seed": 1, "status": "WA", "cost": 0.0, "runtime_ms": 30, "path_length": 0.0},
        ]
        agg = aggregate_case(runs)
        assert agg["success_rate"] == 0.5
        assert agg["failure_rate"] == 0.5

    def test_suite_pass(self):
        from robotjudge.grader import aggregate_suite

        per_case = [
            {"case_id": f"t{i}", "success_rate": 1.0, "failure_rate": 0.0,
             "best_cost": 10.0, "mean_cost": 10.0, "p95_cost": 10.0,
             "best_runtime_ms": 50, "mean_runtime_ms": 50, "p95_runtime_ms": 50}
            for i in range(5)
        ]
        all_runs = [
            {"case_id": f"t{i}", "seed": s, "status": "AC", "runtime_ms": 50}
            for i in range(5)
            for s in range(3)
        ]
        agg = aggregate_suite(per_case, all_runs)
        assert agg["status"] == "PASS"

    def test_suite_fail(self):
        from robotjudge.grader import aggregate_suite

        per_case = [
            {"case_id": "t0", "success_rate": 0.5, "failure_rate": 0.5,
             "best_cost": 10.0, "mean_cost": 10.0, "p95_cost": 10.0,
             "best_runtime_ms": 50, "mean_runtime_ms": 50, "p95_runtime_ms": 50}
        ]
        all_runs = [
            {"case_id": "t0", "seed": 0, "status": "AC", "runtime_ms": 50},
            {"case_id": "t0", "seed": 1, "status": "WA", "runtime_ms": 30},
        ]
        agg = aggregate_suite(per_case, all_runs)
        assert agg["status"] == "FAIL"
