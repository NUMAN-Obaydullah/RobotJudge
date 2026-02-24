#!/usr/bin/env python3
"""Template solver for RobotJudge GridPath.

Copy this file and implement the ``solve()`` function.

Usage:
    python template_solver.py --case <case.json> --seed <int> --out <path.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def solve(case: dict, seed: int) -> list[list[int]]:
    """Solve the grid-pathfinding problem.

    Args:
        case: Parsed case.json dict with keys: grid, start, goal, moves, etc.
        seed: Integer seed for deterministic randomness.

    Returns:
        A list of [row, col] cells from start to goal (inclusive).
    """
    # TODO: Implement your solver here.
    # Example: return [[0,0], [0,1], [1,1]]  # a trivial path
    raise NotImplementedError("Implement your solver!")


def main() -> int:
    parser = argparse.ArgumentParser(description="GridPath solver template")
    parser.add_argument("--case", required=True, help="Path to case.json")
    parser.add_argument("--seed", type=int, required=True, help="Seed for determinism")
    parser.add_argument("--out", required=True, help="Output path.json")
    args = parser.parse_args()

    with open(args.case, "r", encoding="utf-8") as fh:
        case = json.load(fh)

    path_cells = solve(case, args.seed)

    output: dict[str, Any] = {
        "version": "1.0",
        "case_id": case["id"],
        "seed": args.seed,
        "path": path_cells,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, separators=(",", ":"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
