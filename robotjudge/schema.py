"""Schema loading and validation for RobotJudge-CI.

Provides:
- JSON-schema validation for case, path, and results files
- Semantic validation for cases (grid consistency, start/goal validity)
- Semantic validation for paths (legality, bounds, obstacles, start→goal)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import jsonschema

# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

_SCHEMA_CACHE: dict[str, dict] = {}


def _load_schema(name: str) -> dict:
    """Load and cache a JSON schema by base name (e.g. 'case')."""
    if name not in _SCHEMA_CACHE:
        path = _SCHEMA_DIR / f"{name}.schema.json"
        with open(path, "r", encoding="utf-8") as fh:
            _SCHEMA_CACHE[name] = json.load(fh)
    return _SCHEMA_CACHE[name]


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def decode_rle_grid(rle: dict) -> list[list[int]]:
    """Decode an RLE-encoded grid dict into a 2-D matrix."""
    rows, cols = rle["rows"], rle["cols"]
    data_str: str = rle["data"]
    flat: list[int] = []
    for token in data_str.split(","):
        val_s, count_s = token.split(":")
        flat.extend([int(val_s)] * int(count_s))
    if len(flat) != rows * cols:
        raise ValueError(
            f"RLE data length {len(flat)} != rows*cols {rows * cols}"
        )
    return [flat[r * cols : (r + 1) * cols] for r in range(rows)]


def _resolve_grid(case: dict) -> list[list[int]]:
    """Return the grid as a 2-D matrix regardless of encoding."""
    grid = case["grid"]
    if isinstance(grid, dict):
        return decode_rle_grid(grid)
    return grid


# ---------------------------------------------------------------------------
# JSON-schema validation
# ---------------------------------------------------------------------------

def validate_case_schema(data: dict) -> list[str]:
    """Validate *data* against ``case.schema.json``. Return list of errors."""
    schema = _load_schema("case")
    v = jsonschema.Draft202012Validator(schema)
    return [e.message for e in v.iter_errors(data)]


def validate_path_schema(data: dict) -> list[str]:
    """Validate *data* against ``path.schema.json``. Return list of errors."""
    schema = _load_schema("path")
    v = jsonschema.Draft202012Validator(schema)
    return [e.message for e in v.iter_errors(data)]


def validate_results_schema(data: dict) -> list[str]:
    """Validate *data* against ``results.schema.json``. Return list of errors."""
    schema = _load_schema("results")
    v = jsonschema.Draft202012Validator(schema)
    return [e.message for e in v.iter_errors(data)]


# ---------------------------------------------------------------------------
# Semantic validation — case
# ---------------------------------------------------------------------------

def validate_case(data: dict) -> list[str]:
    """Full validation of a case: schema + semantic checks.

    Returns a list of violation strings (empty == valid).
    """
    errors = validate_case_schema(data)
    if errors:
        return errors  # can't do semantic checks on a schema-invalid case

    grid = _resolve_grid(data)
    rows = len(grid)
    cols = len(grid[0])

    # Consistent row widths
    for i, row in enumerate(grid):
        if len(row) != cols:
            errors.append(f"Row {i} has {len(row)} cols, expected {cols}")

    # Start and goal within bounds and on free cells
    sr, sc = data["start"]
    gr, gc = data["goal"]
    for label, r, c in [("start", sr, sc), ("goal", gr, gc)]:
        if not (0 <= r < rows and 0 <= c < cols):
            errors.append(f"{label} ({r},{c}) out of bounds ({rows}x{cols})")
        elif grid[r][c] != 0:
            errors.append(f"{label} ({r},{c}) is on an obstacle")

    # cell_cost dimensions must match grid
    cc = data.get("cell_cost")
    if cc is not None and not isinstance(cc, type(None)):
        if len(cc) != rows:
            errors.append(
                f"cell_cost has {len(cc)} rows, grid has {rows}"
            )
        else:
            for i, row in enumerate(cc):
                if len(row) != cols:
                    errors.append(
                        f"cell_cost row {i} has {len(row)} cols, expected {cols}"
                    )

    return errors


# ---------------------------------------------------------------------------
# Semantic validation — path
# ---------------------------------------------------------------------------

_4N_DELTAS = {(1, 0), (-1, 0), (0, 1), (0, -1)}
_8N_DELTAS = _4N_DELTAS | {(1, 1), (1, -1), (-1, 1), (-1, -1)}

_ACTION_TO_DELTA: dict[str, tuple[int, int]] = {
    "U": (-1, 0),
    "D": (1, 0),
    "L": (0, -1),
    "R": (0, 1),
    "UL": (-1, -1),
    "UR": (-1, 1),
    "DL": (1, -1),
    "DR": (1, 1),
}


def _resolve_path_cells(
    path_field: list, start: list[int]
) -> list[tuple[int, int]] | None:
    """Convert a path field to a list of (row, col) cells.

    Returns None if the format is unrecognised.
    """
    if not path_field:
        return None
    if isinstance(path_field[0], list):
        # Cell-list mode
        return [(c[0], c[1]) for c in path_field]
    if isinstance(path_field[0], str):
        # Action-list mode — reconstruct cells
        cells = [(start[0], start[1])]
        r, c = start
        for action in path_field:
            dr, dc = _ACTION_TO_DELTA[action]
            r, c = r + dr, c + dc
            cells.append((r, c))
        return cells
    return None


def validate_path(
    path_data: dict,
    case_data: dict,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate solver output against the case.

    Returns ``(valid, violations, metrics)`` where *metrics* includes
    ``path_length``, ``cost``, ``collision``, ``reached_goal``.
    """
    violations: list[str] = []
    metrics: dict[str, Any] = {
        "path_length": 0.0,
        "cost": 0.0,
        "collision": False,
        "reached_goal": False,
    }

    # Schema check first
    schema_errors = validate_path_schema(path_data)
    if schema_errors:
        return False, schema_errors, metrics

    grid = _resolve_grid(case_data)
    rows = len(grid)
    cols = len(grid[0])
    moves = case_data["moves"]
    allowed = _8N_DELTAS if moves == "8N" else _4N_DELTAS
    start = case_data["start"]
    goal = case_data["goal"]
    cell_cost_map = case_data.get("cell_cost")
    max_path_len = (
        case_data.get("limits", {}).get("max_path_len")
    )

    cells = _resolve_path_cells(path_data["path"], start)
    if cells is None:
        violations.append("Unrecognised path format")
        return False, violations, metrics

    # Check start
    if cells[0] != (start[0], start[1]):
        violations.append(
            f"Path starts at {cells[0]}, expected {tuple(start)}"
        )

    # Check goal
    if cells[-1] == (goal[0], goal[1]):
        metrics["reached_goal"] = True
    else:
        violations.append(
            f"Path ends at {cells[-1]}, expected {tuple(goal)}"
        )

    # Walk the path
    path_length = 0.0
    cost = 0.0
    collision = False
    safety_violations = []

    for i in range(len(cells)):
        r, c = cells[i]
        # Bounds check
        if not (0 <= r < rows and 0 <= c < cols):
            violations.append(f"Cell {i} ({r},{c}) out of bounds")
            continue
        # Obstacle check
        if grid[r][c] != 0:
            violations.append(f"Cell {i} ({r},{c}) is an obstacle")
            collision = True
        
        # Step legality + length/cost
        if i > 0:
            pr, pc = cells[i - 1]
            dr, dc = r - pr, c - pc
            if (dr, dc) not in allowed:
                violations.append(
                    f"Step {i-1}→{i} ({pr},{pc})→({r},{c}) illegal under {moves}"
                )
            is_diag = abs(dr) + abs(dc) == 2
            step_cost = math.sqrt(2) if is_diag else 1.0
            path_length += step_cost
            if cell_cost_map is not None:
                cost += step_cost + cell_cost_map[r][c]
            else:
                cost += step_cost

        # Kinematic Safety Constraint (REQ-7): Prevent infinite angular acceleration
        if i > 1:
            pr2, pc2 = cells[i - 2]
            pr1, pc1 = cells[i - 1]
            cr, cc = cells[i]
            
            dr1, dc1 = pr1 - pr2, pc1 - pc2
            dr2, dc2 = cr - pr1, cc - pc1
            # Check for immediate 180-degree reversal
            if dr1 == -dr2 and dc1 == -dc2 and (dr1 != 0 or dc1 != 0):
                safety_violations.append(f"Safety violation at step {i}: Kinematic 180-degree reversal")

    metrics["path_length"] = path_length
    metrics["cost"] = cost if cell_cost_map is not None else path_length
    metrics["collision"] = collision
    metrics["safety_violations_count"] = len(safety_violations)
    
    if safety_violations:
        violations.extend(safety_violations)

    # max_path_len check (geometric length)
    if max_path_len is not None and len(cells) - 1 > max_path_len:
        violations.append(
            f"Path has {len(cells)-1} steps, exceeds max_path_len {max_path_len}"
        )

    valid = len(violations) == 0
    return valid, violations, metrics
