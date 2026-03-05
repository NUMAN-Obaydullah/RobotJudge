# Requirements Verification Checklist

## Requirement 1: Execution Engine & Pipeline (REQ-1 & REQ-6)

**Statement:**
The paper claims Docker-based execution, resource tracking, and a full evaluation pipeline (Submission -> Container -> Seeds -> Evaluation -> Aggregation).

**Achieved:**
We built the sandbox mode which spins up isolated containers, sets strict CPU/Memory limits, measures peak memory using psutil, and enforces strict wall-clock time limits (TLE verdicts). The pipeline is fully handled sequentially by server.py and runner.py.

## Requirement 2: Seed Governance & Statistics (REQ-2 & REQ-4)

**Statement:**
The paper claims seed range configuration and statistical verdicts including P95 runtimes.

**Achieved:**
The web UI accepts a seed range, iterates the solver over each seed individually, and aggregates cross-seed status. We explicitly implemented P95 runtime and Mean Cost calculations across all seeds and displayed them on the Dashboard.

## Requirement 3: Oracle/Validator Separation (REQ-3)

**Statement:**
The paper claims the scenario generation is separated from validation.

**Achieved:**
We have testcases generation scripts separated entirely from the grader. The grader purely acts as an Oracle, reading the solver's output relative to the environment without generating anything itself.

## Requirement 4: Artifact & Traceability (REQ-5)

**Statement:**
The paper mentions logs, historical storage, traceability, and versioned problems.

**Achieved:**
The database stores rich historical records (Run, ResultSet, PathRecord). Submissions and JSON logs are saved to disk. We also implemented explicit versioning (e.g. v1.0) for testcases in the Problem Registry database and UI.

## Requirement 5: Safety Constraints (REQ-7)

**Statement:**
The paper claims enforcement of safety constraints for physical pathing.

**Achieved:**
The path validation actively prohibits and fails submissions attempting instantaneous 180-degree phase reversals, preventing infinite angular acceleration. This ensures grid outputs map to executable real-world physical boundaries.
