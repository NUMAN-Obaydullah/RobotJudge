# Submission Contract (GridPath) — v1.0

## 1) Entrypoint
Your solver must be runnable as a CLI:

    python my_solver.py --case /path/to/case.json --seed 42 --out /path/to/path.json

Required args:
- `--case`: path to input testcase (`case.json`)
- `--seed`: integer seed for deterministic randomness
- `--out`: path to output file (`path.json`)

## 2) Determinism requirement
Given identical `case.json` and identical `--seed`, your solver must produce:
- either identical output, or output that is equivalent under the validity rules
- and must not depend on wall-clock time or external randomness

## 3) Output format
Write `path.json` matching `schemas/path.schema.json`.

Supported `path` formats:
- Cell list: `[[r,c], [r,c], ...]` (recommended)
- Action list: `["U","R",...]` or diagonals (`"UR"`, etc.)

## 4) Performance
Your solver must complete within runner limits (time/memory). If it exceeds:
- time ⇒ TLE
- memory ⇒ MLE
- crash/no output ⇒ RTE

## 5) Forbidden behavior
- Network calls
- Writing outside the provided output path
- Reading anything except the provided testcase file (unless explicitly allowed)
