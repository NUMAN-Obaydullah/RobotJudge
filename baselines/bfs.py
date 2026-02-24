#!/usr/bin/env python3
"""BFS baseline solver for RobotJudge GridPath.

Usage:
    python bfs.py --case <case.json> --seed <int> --out <path.json>

Breadth-First Search — finds the shortest-hop path (fewest cells).
On uniform-cost grids this is optimal; on weighted grids it finds a
valid but potentially suboptimal path.

Supports:
  - 4N and 8N movement
  - Matrix and RLE grid formats
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
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
# BFS search
# ---------------------------------------------------------------------------

def bfs(case: dict, seed: int) -> list[list[int]]:
    """Run BFS and return a cell-list path."""
    grid = resolve_grid(case)
    rows = len(grid)
    cols = len(grid[0])
    moves = case["moves"]
    sr, sc = case["start"]
    gr, gc = case["goal"]

    if moves == "8N":
        deltas = [(0, 1), (0, -1), (1, 0), (-1, 0),
                  (1, 1), (1, -1), (-1, 1), (-1, -1)]
    else:
        deltas = [(0, 1), (0, -1), (1, 0), (-1, 0)]

    visited = [[False] * cols for _ in range(rows)]
    visited[sr][sc] = True
    parent: dict[tuple[int, int], tuple[int, int] | None] = {(sr, sc): None}

    queue: deque[tuple[int, int]] = deque()
    queue.append((sr, sc))

    while queue:
        r, c = queue.popleft()

        if (r, c) == (gr, gc):
            # Reconstruct path
            path: list[list[int]] = []
            node: tuple[int, int] | None = (gr, gc)
            while node is not None:
                path.append(list(node))
                node = parent[node]
            path.reverse()
            return path

        for dr, dc in deltas:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if grid[nr][nc] != 0:
                continue
            if visited[nr][nc]:
                continue

            visited[nr][nc] = True
            parent[(nr, nc)] = (r, c)
            queue.append((nr, nc))

    raise RuntimeError(f"No path found from {case['start']} to {case['goal']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="BFS baseline solver")
    parser.add_argument("--case", required=True, help="Path to case.json")
    parser.add_argument("--seed", type=int, required=True, help="Seed (unused for BFS)")
    parser.add_argument("--out", required=True, help="Output path.json")
    args = parser.parse_args()

    with open(args.case, "r", encoding="utf-8") as fh:
        case = json.load(fh)

    path_cells = bfs(case, args.seed)

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
