"""Deterministic testcase generator for RobotJudge-CI.

Reads a suite configuration YAML and produces grid-pathfinding testcases
in ``testcases/<suite>/<tier>/<id>/case.json`` (+ ``meta.json``).

Supported families:
  random_field, corridors, rooms_doors, maze, traps, narrow_passages, high_density
"""

from __future__ import annotations

import json
import math
import random as _random_mod
from collections import deque
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lerp(rng: _random_mod.Random, lo: float, hi: float) -> float:
    return lo + rng.random() * (hi - lo)


def _pick_grid_size(
    rng: _random_mod.Random, sizes: list[list[int]]
) -> tuple[int, int]:
    lo, hi = sizes[0], sizes[-1]
    rows = rng.randint(lo[0], hi[0])
    cols = rng.randint(lo[1], hi[1])
    return rows, cols


def _bfs_reachable(
    grid: list[list[int]], start: tuple[int, int], goal: tuple[int, int]
) -> bool:
    """BFS check that *goal* is reachable from *start* (8-connected)."""
    rows, cols = len(grid), len(grid[0])
    visited = set()
    queue = deque([start])
    visited.add(start)
    while queue:
        r, c = queue.popleft()
        if (r, c) == goal:
            return True
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in visited and grid[nr][nc] == 0:
                    visited.add((nr, nc))
                    queue.append((nr, nc))
    return False


def _pick_start_goal(
    rng: _random_mod.Random,
    grid: list[list[int]],
    min_manhattan: int,
    max_manhattan: int,
    max_attempts: int = 2000,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Pick a random (start, goal) pair that is reachable and within Manhattan distance range."""
    rows, cols = len(grid), len(grid[0])
    free_cells: list[tuple[int, int]] = []
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == 0:
                free_cells.append((r, c))
    if len(free_cells) < 2:
        raise ValueError("Grid has fewer than 2 free cells")

    for _ in range(max_attempts):
        s = free_cells[rng.randint(0, len(free_cells) - 1)]
        g = free_cells[rng.randint(0, len(free_cells) - 1)]
        if s == g:
            continue
        md = abs(s[0] - g[0]) + abs(s[1] - g[1])
        if md < min_manhattan or md > max_manhattan:
            continue
        if _bfs_reachable(grid, s, g):
            return s, g

    # Fallback: relax distance constraints
    for _ in range(max_attempts):
        s = free_cells[rng.randint(0, len(free_cells) - 1)]
        g = free_cells[rng.randint(0, len(free_cells) - 1)]
        if s != g and _bfs_reachable(grid, s, g):
            return s, g
    raise ValueError("Cannot find reachable start/goal pair")


# ---------------------------------------------------------------------------
# Grid family generators
# ---------------------------------------------------------------------------

def _gen_random_field(
    rng: _random_mod.Random,
    rows: int,
    cols: int,
    params: dict,
) -> list[list[int]]:
    lo, hi = params.get("obstacle_density", [0.15, 0.25])
    density = _lerp(rng, lo, hi)
    return [
        [1 if rng.random() < density else 0 for _ in range(cols)]
        for _ in range(rows)
    ]


def _gen_corridors(
    rng: _random_mod.Random,
    rows: int,
    cols: int,
    params: dict,
) -> list[list[int]]:
    lo, hi = params.get("corridor_width", [2, 4])
    cw = rng.randint(lo, hi)
    grid = [[1] * cols for _ in range(rows)]
    # Horizontal corridors
    r = 0
    while r < rows:
        for dr in range(min(cw, rows - r)):
            for c in range(cols):
                grid[r + dr][c] = 0
        r += cw + rng.randint(1, 3)
    # Vertical connectors
    for c in range(0, cols, rng.randint(5, 15)):
        for r in range(rows):
            for dc in range(min(cw, cols - c)):
                if c + dc < cols:
                    grid[r][c + dc] = 0
    return grid


def _gen_rooms_doors(
    rng: _random_mod.Random,
    rows: int,
    cols: int,
    params: dict,
) -> list[list[int]]:
    lo_rooms, hi_rooms = params.get("rooms", [3, 6])
    lo_dw, hi_dw = params.get("door_width", [1, 2])
    n_rooms_h = rng.randint(lo_rooms, hi_rooms)
    n_rooms_v = rng.randint(lo_rooms, hi_rooms)
    grid = [[0] * cols for _ in range(rows)]

    # Draw walls, then punch doors
    h_walls: list[int] = sorted(rng.sample(range(2, rows - 2), min(n_rooms_v - 1, rows - 4)))
    v_walls: list[int] = sorted(rng.sample(range(2, cols - 2), min(n_rooms_h - 1, cols - 4)))

    for wr in h_walls:
        for c in range(cols):
            grid[wr][c] = 1
        # Punch doors
        n_doors = rng.randint(1, 3)
        for _ in range(n_doors):
            dc = rng.randint(0, cols - 1)
            dw = rng.randint(lo_dw, hi_dw)
            for d in range(dw):
                if dc + d < cols:
                    grid[wr][dc + d] = 0

    for wc in v_walls:
        for r in range(rows):
            grid[r][wc] = 1
        n_doors = rng.randint(1, 3)
        for _ in range(n_doors):
            dr = rng.randint(0, rows - 1)
            dw = rng.randint(lo_dw, hi_dw)
            for d in range(dw):
                if dr + d < rows:
                    grid[dr + d][wc] = 0
    return grid


def _gen_maze(
    rng: _random_mod.Random,
    rows: int,
    cols: int,
    params: dict,
) -> list[list[int]]:
    """Generate a maze using randomized DFS (recursive backtracker).
    
    Works in a cell grid where odd-indexed positions are passages and
    even-indexed positions are walls.  Then optionally 'braid' by removing
    some dead-ends.
    """
    # Ensure odd dimensions for clean maze structure
    mr = rows if rows % 2 == 1 else rows - 1
    mc = cols if cols % 2 == 1 else cols - 1
    grid = [[1] * cols for _ in range(rows)]

    # Carve maze in the odd-indexed sub-grid
    def _in_bounds(r: int, c: int) -> bool:
        return 0 <= r < mr and 0 <= c < mc

    stack: list[tuple[int, int]] = [(1, 1)]
    grid[1][1] = 0
    visited_maze = {(1, 1)}
    directions = [(0, 2), (0, -2), (2, 0), (-2, 0)]

    while stack:
        cr, cc = stack[-1]
        rng.shuffle(directions)
        found = False
        for dr, dc in directions:
            nr, nc = cr + dr, cc + dc
            if _in_bounds(nr, nc) and (nr, nc) not in visited_maze:
                # Carve wall between
                grid[(cr + nr) // 2][(cc + nc) // 2] = 0
                grid[nr][nc] = 0
                visited_maze.add((nr, nc))
                stack.append((nr, nc))
                found = True
                break
        if not found:
            stack.pop()

    # Braid: remove some dead-ends
    lo_bf, hi_bf = params.get("braid_factor", [0.0, 0.1])
    braid = _lerp(rng, lo_bf, hi_bf)
    if braid > 0:
        for r in range(1, mr, 2):
            for c in range(1, mc, 2):
                if grid[r][c] != 0:
                    continue
                # Count walls around
                neighbors_wall = []
                for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < mr and 0 <= nc < mc and grid[nr][nc] == 1:
                        neighbors_wall.append((nr, nc))
                if len(neighbors_wall) == 3 and rng.random() < braid:
                    # Dead-end — remove a random wall
                    wr, wc = rng.choice(neighbors_wall)
                    grid[wr][wc] = 0
    return grid


def _gen_traps(
    rng: _random_mod.Random,
    rows: int,
    cols: int,
    params: dict,
) -> list[list[int]]:
    """Open field with dead-end pockets that lure greedy solvers."""
    grid = [[0] * cols for _ in range(rows)]
    lo_de, hi_de = params.get("deadend_ratio", [0.2, 0.4])
    de_ratio = _lerp(rng, lo_de, hi_de)
    n_traps = int(de_ratio * (rows + cols) / 2)
    for _ in range(n_traps):
        tr = rng.randint(2, rows - 3)
        tc = rng.randint(2, cols - 3)
        length = rng.randint(3, min(10, rows - 2, cols - 2))
        direction = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        # Draw a dead-end corridor
        for step in range(length):
            nr = tr + direction[0] * step
            nc = tc + direction[1] * step
            if 0 <= nr < rows and 0 <= nc < cols:
                # Walls on sides
                for perp in [-1, 1]:
                    wr = nr + direction[1] * perp
                    wc = nc + direction[0] * perp
                    if 0 <= wr < rows and 0 <= wc < cols:
                        grid[wr][wc] = 1
    return grid


def _gen_narrow_passages(
    rng: _random_mod.Random,
    rows: int,
    cols: int,
    params: dict,
) -> list[list[int]]:
    """Dense obstacles with narrow passages carved through."""
    grid = [[1] * cols for _ in range(rows)]
    lo_pw, hi_pw = params.get("passage_width", [1, 2])
    pw = rng.randint(lo_pw, hi_pw)
    # Carve random walks to create narrow passages
    n_walks = rng.randint(rows // 4, rows // 2)
    for _ in range(n_walks):
        r, c = rng.randint(0, rows - 1), rng.randint(0, cols - 1)
        walk_len = rng.randint(rows, rows * 3)
        for _ in range(walk_len):
            for dr in range(pw):
                for dc in range(pw):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < rows and 0 <= cc < cols:
                        grid[rr][cc] = 0
            direction = rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
            r = max(0, min(rows - 1, r + direction[0]))
            c = max(0, min(cols - 1, c + direction[1]))
    return grid


def _gen_high_density(
    rng: _random_mod.Random,
    rows: int,
    cols: int,
    params: dict,
) -> list[list[int]]:
    """High obstacle density random field."""
    lo, hi = params.get("obstacle_density", [0.28, 0.35])
    density = _lerp(rng, lo, hi)
    return [
        [1 if rng.random() < density else 0 for _ in range(cols)]
        for _ in range(rows)
    ]


_FAMILY_MAP = {
    "random_field": _gen_random_field,
    "corridors": _gen_corridors,
    "rooms_doors": _gen_rooms_doors,
    "maze": _gen_maze,
    "traps": _gen_traps,
    "narrow_passages": _gen_narrow_passages,
    "high_density": _gen_high_density,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_suite_config(config_path: str | Path) -> dict:
    """Load and return a suite configuration YAML."""
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _ensure_solvable(
    rng: _random_mod.Random,
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
    max_retries: int = 50,
) -> list[list[int]]:
    """If grid is not solvable, do random obstacle removal until it is."""
    if _bfs_reachable(grid, start, goal):
        return grid
    rows, cols = len(grid), len(grid[0])
    for _ in range(max_retries):
        # Random walk from start, clearing obstacles
        r, c = start
        while (r, c) != goal:
            grid[r][c] = 0
            dr = 1 if goal[0] > r else (-1 if goal[0] < r else 0)
            dc = 1 if goal[1] > c else (-1 if goal[1] < c else 0)
            # Add some randomness
            if rng.random() < 0.3:
                dr = rng.choice([-1, 0, 1])
            if rng.random() < 0.3:
                dc = rng.choice([-1, 0, 1])
            r = max(0, min(rows - 1, r + dr))
            c = max(0, min(cols - 1, c + dc))
        grid[goal[0]][goal[1]] = 0
        if _bfs_reachable(grid, start, goal):
            return grid
    # Last resort: clear a straight-ish path
    r, c = start
    while (r, c) != goal:
        grid[r][c] = 0
        if r < goal[0]:
            r += 1
        elif r > goal[0]:
            r -= 1
        elif c < goal[1]:
            c += 1
        elif c > goal[1]:
            c -= 1
    grid[goal[0]][goal[1]] = 0
    return grid


def generate_suite(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    master_seed: int = 42,
) -> list[Path]:
    """Generate the full testcase suite from a config YAML.

    Returns paths to all generated ``case.json`` files.
    """
    cfg = load_suite_config(config_path)
    output_dir = Path(output_dir)
    suite_rng = _random_mod.Random(master_seed)
    generated: list[Path] = []

    moves = cfg["problem"]["moves"]
    enforce_solvable = cfg["problem"].get("enforce_solvable", True)
    limits = cfg.get("limits", {})
    seed_policy = cfg.get("seed_policy", {"type": "range", "start": 0, "count": 100})

    for tier in cfg["tiers"]:
        tier_name = tier["name"]
        total_cases = tier["cases"]
        grid_sizes = tier["grid_sizes"]
        families = tier["families"]
        sg_cfg = tier.get("start_goal", {})
        min_manhattan = sg_cfg.get("min_manhattan", 10)
        max_manhattan = sg_cfg.get("max_manhattan", 9999)

        # Compute how many cases per family based on weight
        weights = [f["weight"] for f in families]
        total_w = sum(weights)
        counts: list[int] = []
        remaining = total_cases
        for i, f in enumerate(families):
            if i == len(families) - 1:
                counts.append(remaining)
            else:
                n = max(1, round(total_cases * f["weight"] / total_w))
                counts.append(n)
                remaining -= n

        case_idx = 0
        for fam_cfg, fam_count in zip(families, counts):
            family_name = fam_cfg["family"]
            gen_fn = _FAMILY_MAP.get(family_name)
            if gen_fn is None:
                raise ValueError(f"Unknown family: {family_name}")

            for _ in range(fam_count):
                case_seed = suite_rng.randint(0, 2**31 - 1)
                case_rng = _random_mod.Random(case_seed)
                rows, cols = _pick_grid_size(case_rng, grid_sizes)
                grid = gen_fn(case_rng, rows, cols, fam_cfg)

                # Pick start/goal
                start, goal = _pick_start_goal(
                    case_rng, grid, min_manhattan, max_manhattan
                )

                # Ensure solvability
                if enforce_solvable:
                    grid = _ensure_solvable(case_rng, grid, start, goal)

                # Ensure start and goal are free
                grid[start[0]][start[1]] = 0
                grid[goal[0]][goal[1]] = 0

                case_id = f"{tier_name}_{case_idx:04d}"
                case_dir = output_dir / tier_name / case_id
                case_dir.mkdir(parents=True, exist_ok=True)

                case_data: dict[str, Any] = {
                    "version": "1.0",
                    "id": case_id,
                    "grid": grid,
                    "start": list(start),
                    "goal": list(goal),
                    "moves": moves,
                    "limits": limits,
                    "seed_policy": seed_policy,
                    "meta": {
                        "family": family_name,
                        "tier": tier_name,
                        "generator_seed": case_seed,
                        "difficulty": tier_name,
                        "grid_size": [rows, cols],
                    },
                }

                case_path = case_dir / "case.json"
                with open(case_path, "w", encoding="utf-8") as fh:
                    json.dump(case_data, fh, separators=(",", ":"))

                meta_path = case_dir / "meta.json"
                with open(meta_path, "w", encoding="utf-8") as fh:
                    json.dump(case_data["meta"], fh, indent=2)

                generated.append(case_path)
                case_idx += 1

    return generated
