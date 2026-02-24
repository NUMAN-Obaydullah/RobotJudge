#!/usr/bin/env python3
"""Dijkstra baseline solver for RobotJudge GridPath.

Usage:
    python dijkstra.py --case <case.json> --seed <int> --out <path.json>

Dijkstra's algorithm — finds the optimal shortest-cost path without
using a heuristic.  Explores more nodes than A* but guarantees optimality
on both uniform and weighted grids.

Supports:
  - 4N and 8N movement
  - Matrix and RLE grid formats
  - cell_cost weighted grids
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Grid decode
# ---------------------------------------------------------------------------

def decode_rle_grid(rle: dict) -> list[list[int]]:
    rows, cols = rle["rows"], rle["cols"]
    flat: list[int] = []
    for token in rle["data"].split(","):
        val_s, count_s = token.split(":")
        flat.extend([int(val_s)] * int(count_s))
    return [flat[r * cols : (r + 1) * cols] for r in range(rows)]


def resolve_grid(case: dict) -> list[list[int]]:
    grid = case["grid"]
    return decode_rle_grid(grid) if isinstance(grid, dict) else grid


# ---------------------------------------------------------------------------
# Dijkstra search
# ---------------------------------------------------------------------------

def dijkstra(case: dict, seed: int) -> list[list[int]]:
    """Run Dijkstra and return a cell-list path."""
    grid = resolve_grid(case)
    rows = len(grid)
    cols = len(grid[0])
    moves = case["moves"]
    sr, sc = case["start"]
    gr, gc = case["goal"]
    cell_cost_map = case.get("cell_cost")

    if moves == "8N":
        deltas = [(0, 1), (0, -1), (1, 0), (-1, 0),
                  (1, 1), (1, -1), (-1, 1), (-1, -1)]
    else:
        deltas = [(0, 1), (0, -1), (1, 0), (-1, 0)]

    # Priority queue: (cost, tie_breaker, r, c)
    open_set: list[tuple[float, int, int, int]] = [(0.0, 0, sr, sc)]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {(sr, sc): None}
    dist: dict[tuple[int, int], float] = {(sr, sc): 0.0}
    tie = 0

    while open_set:
        cost, _, r, c = heapq.heappop(open_set)

        if (r, c) == (gr, gc):
            # Reconstruct
            path: list[list[int]] = []
            node: tuple[int, int] | None = (gr, gc)
            while node is not None:
                path.append(list(node))
                node = came_from[node]
            path.reverse()
            return path

        if cost > dist.get((r, c), float("inf")):
            continue  # stale entry

        for dr, dc in deltas:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if grid[nr][nc] != 0:
                continue

            is_diag = abs(dr) + abs(dc) == 2
            step_cost = math.sqrt(2) if is_diag else 1.0
            if cell_cost_map is not None:
                step_cost += cell_cost_map[nr][nc]

            new_cost = cost + step_cost
            if new_cost < dist.get((nr, nc), float("inf")):
                dist[(nr, nc)] = new_cost
                tie += 1
                heapq.heappush(open_set, (new_cost, tie, nr, nc))
                came_from[(nr, nc)] = (r, c)

    raise RuntimeError(f"No path found from {case['start']} to {case['goal']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Dijkstra baseline solver")
    parser.add_argument("--case", required=True, help="Path to case.json")
    parser.add_argument("--seed", type=int, required=True, help="Seed (unused for Dijkstra)")
    parser.add_argument("--out", required=True, help="Output path.json")
    args = parser.parse_args()

    with open(args.case, "r", encoding="utf-8") as fh:
        case = json.load(fh)

    path_cells = dijkstra(case, args.seed)

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
