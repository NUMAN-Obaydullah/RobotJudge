# RobotJudge-CI Scoring Contract (GridPath) — v1.0

## 1) Status codes
- **AC**: valid path found and within limits
- **WA**: invalid output or invalid path
- **TLE**: exceeded time limit
- **MLE**: exceeded memory limit (if enforced)
- **RTE**: runtime error / no output / malformed JSON

## 2) Validity rules (WA if any fail)
A run is **valid** only if:
1. Output JSON validates against `schemas/path.schema.json`
2. Path starts at the testcase `start` and ends at `goal` (cell-list mode), OR action-list mode reconstructs a path that satisfies this.
3. Every step is legal under `moves`:
   - `4N`: (±1,0) or (0,±1)
   - `8N`: also allows diagonals (±1,±1)
4. All visited cells are within bounds.
5. No visited cell is an obstacle (`grid[r][c] == 1`).
6. Path length does not exceed `limits.max_path_len` if provided.

## 3) Cost function (per run)
- If `cell_cost` is absent/null:
  - **cost = path_length**
  - `4N` step cost = 1
  - `8N` diagonal step cost = √2 (contract default)
- If `cell_cost` is provided:
  - **cost = sum(step_cost + cell_cost[next_cell])**
  - step_cost as above

The judge records:
- `path_length` (geometric length with √2 diagonals)
- `cost` (weighted if applicable)

## 4) Limits (TLE/MLE)
- `limits.time_ms` and `limits.mem_mb` may be included in testcase or suite.
- Runner-enforced limits override testcase limits if stricter.

## 5) Multi-seed aggregation (robustness)
For each testcase run over K seeds:
- `success_rate = (#AC) / K`
- `failure_rate = 1 - success_rate`
- `best_cost = min(cost over AC runs)`
- `mean_cost = mean(cost over AC runs)` (if no AC runs, undefined -> set to +INF in implementation)
- `p95_cost = 95th percentile(cost over AC runs)` (robust cost)
- `p95_runtime_ms = 95th percentile(runtime_ms over all completed runs)`

## 6) Suite aggregation and PASS/FAIL gate
### Gate (default)
- PASS only if `suite_success_rate >= 0.95`
  - `suite_success_rate = (sum AC over all case×seed) / (total runs)`

### Suite score (default)
- `suite_score = Σ_i (w_i * p95_cost_i) + λ * Σ_i (w_i * p95_runtime_ms_i) + P_fail`
  - `w_i`: testcase weight (default 1.0)
  - `λ`: runtime tradeoff coefficient (default 0.001)
  - `P_fail`: penalty for failures (default: `1e6 * Σ_i (w_i * failure_rate_i)`)

All constants (`λ`, penalties, gate threshold) are contract parameters and must be recorded in the report for traceability.
