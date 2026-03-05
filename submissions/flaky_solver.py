#!/usr/bin/env python3
"""Flaky solver for demonstrating RobotJudge-CI features.

This solver intentionally generates varying verdicts (AC, WA, TLE)
based on the provided seed, to demonstrate how the continuous
integration system handles and aggregations different failure modes.

Usage:
    python flaky_solver.py --case <case.json> --seed <int> --out <path.json>
"""

import argparse
import heapq
import json
import math
import sys
import time
from pathlib import Path


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


def heuristic(r: int, c: int, gr: int, gc: int, moves: str) -> float:
    dr = abs(r - gr)
    dc = abs(c - gc)
    if moves == "8N":
        return max(dr, dc) + (math.sqrt(2) - 1) * min(dr, dc)
    return float(dr + dc)


def astar_correct(case: dict) -> list[list[int]]:
    """A standard correct A* search for the AC cases."""
    grid = resolve_grid(case)
    rows = len(grid)
    cols = len(grid[0])
    moves = case.get("moves", "8N")
    sr, sc = case["start"]
    gr, gc = case["goal"]

    if moves == "8N":
        deltas = [(0, 1), (0, -1), (1, 0), (-1, 0),
                  (1, 1), (1, -1), (-1, 1), (-1, -1)]
    else:
        deltas = [(0, 1), (0, -1), (1, 0), (-1, 0)]

    start_h = heuristic(sr, sc, gr, gc, moves)
    open_set = [(start_h, 0.0, 0, sr, sc)]
    came_from = {(sr, sc): None}
    g_score = {(sr, sc): 0.0}
    tie = 0

    while open_set:
        f, g, _, r, c = heapq.heappop(open_set)

        if (r, c) == (gr, gc):
            path = []
            node = (gr, gc)
            while node is not None:
                path.append(list(node))
                node = came_from[node]
            path.reverse()
            return path

        if g > g_score.get((r, c), float("inf")):
            continue

        for dr, dc in deltas:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                if grid[nr][nc] == 1:
                    continue
                cost_g = 1.0 if dr == 0 or dc == 0 else math.sqrt(2)
                tentative_g = g + cost_g
                if tentative_g < g_score.get((nr, nc), float("inf")):
                    came_from[(nr, nc)] = (r, c)
                    g_score[(nr, nc)] = tentative_g
                    f_score = tentative_g + heuristic(nr, nc, gr, gc, moves)
                    tie += 1
                    heapq.heappush(open_set, (f_score, tentative_g, tie, nr, nc))

    return [] # No path found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.case, "r", encoding="utf-8") as fh:
        case_data = json.load(fh)

    # To demonstrate CI features, assign verdicts deterministically based on seed
    # Seed 0: AC (Correct A*)
    # Seed 1: WA (Wrong Answer - Straight line ignoring obstacles)
    # Seed 2: TLE (Time Limit Exceeded - Infinite loop / sleep)
    
    behavior_mode = args.seed % 3
    
    if behavior_mode == 0:
        # ACCEPTED (AC)
        path = astar_correct(case_data)
    
    elif behavior_mode == 1:
        # WRONG ANSWER (WA) - Just yield START and GOAL directly without checking grid
        sr, sc = case_data["start"]
        gr, gc = case_data["goal"]
        path = [[sr, sc], [gr, gc]]
        
    else:
        # TIME LIMIT EXCEEDED (TLE)
        time.sleep(15)  # Sleep well beyond the timeout limit
        path = []

    # Write output artifact
    out_obj = {
        "status": "success" if path else "no_path",
        "path": path,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out_obj, fh, indent=2)


if __name__ == "__main__":
    main()
