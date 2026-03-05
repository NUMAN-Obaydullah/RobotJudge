# RobotJudge-CI Analysis and Next-Phase Development Plan

## Current Implementation Overview

### System Structure and Implemented Features

**Project Architecture:** The RobotJudge-CI project is a Python-based judging system organized as a Python package (`robotjudge`) with dedicated modules for core functionality. The command-line interface supports subcommands for generating test cases, running submissions, and validating files. A set of baseline solver scripts (e.g., A*, BFS, Dijkstra) is included for reference and testing, along with a template solver for participants. The system defines JSON schemas for test cases, solution output, and aggregated results, ensuring that inputs and outputs adhere to a standard format.

**Web Interface:** In addition to the CLI tools, RobotJudge-CI includes a web server built with FastAPI (see `web/server.py`) that provides a simple web UI. This web component serves static pages for viewing problems, submitting solutions, and checking status, and exposes REST API endpoints for retrieving test case data, viewing results/reports, and uploading solutions. A SQLite/PostgreSQL-backed ORM layer (via SQLAlchemy) is used to store test cases, solver code submissions, and result records for persistence. On startup, the server initializes the database schema if needed. When a user uploads a solver through the web UI, the server saves the file, records a job in the database, and triggers an asynchronous execution of the judge on that submission. The web UI allows monitoring the job status and viewing the final report once grading is complete. This integrated web system effectively provides an “AOJ v3 style” interface for an automated online judge experience, albeit currently targeting a single path-planning problem.

**Features Implemented:** The judge can execute a submitted Python solver on a suite of grid-based pathfinding test cases, enforcing a strict interface: the solver must accept command-line arguments for the test case file, a random seed, and an output path. Deterministic behavior is required – given the same input and seed, the solver should produce the same path every time. The judge runner (`robotjudge.runner`) handles launching the solver process for each test case and seed, captures its output, and measures execution time. After each run, the grader module validates the solver’s output path and assigns a status code. The framework supports multiple runs per test case (with different random seeds) to evaluate solution robustness. Reports are automatically generated in both JSON and Markdown formats, summarizing results per test and overall.

### CI/CD Integration Status

**Continuous Integration Workflow:** The project includes a GitHub Actions workflow (`.github/workflows/judge.yml`) that automates testing and basic judging on every push/PR. The CI workflow is split into two jobs: (1) Unit Tests & Schema Validation, which installs the package and runs the Pytest test suite, and (2) Judge – Baseline & Submissions, which depends on the tests passing. In the judging job, the CI installs the `robotjudge` package and then performs a baseline sanity check by running the provided A* baseline solver on the public test suite. It then verifies that the baseline’s aggregated result is a PASS. Next, a determinism gate runs the same baseline twice on a small sample of cases and seeds, then uses a script to compare the two result sets. Finally, the CI always uploads the generated reports as artifacts for inspection.

**CI/CD Improvement Opportunities:** Currently, the CI focuses on core correctness and determinism. Additional baseline solvers could be automatically run on subsets of test cases. Integration tests for the web API could be added to verify that the server and database functionality work. Another improvement is building the Docker image as part of CI to ensure the containerized environment is up-to-date. Setting up an automated deployment could be a future CI/CD extension. Lastly, adding linting or type-checking and tracking test coverage would increase confidence in ongoing development.

### Path Planning Evaluation Logic and Test Case Design

**Test Case Format:** Each test case is a JSON file containing a grid definition and related parameters. The grid is a 2D array with 0 for free cells and 1 for obstacles. A start coordinate and goal coordinate are specified, along with the allowed movement model (`4N` or `8N`). The test case may also include a `cell_cost` map for weighted terrains, and optional limits for time, memory, or path length.

**Test Suite Organization:** Test cases are grouped by difficulty tier (e.g., easy, medium, hard), each generated according to predefined parameters in a YAML config (`configs/public_suite.yaml`).

**Evaluation Procedure:** For each (test case, seed) pair, the judge invokes the solver and captures its output path. The grader logic then validates the output. If valid, the run is marked as AC (Accepted) and records the path length and cost. Otherwise, it is marked as WA, RTE, or TLE.

### Limitations and Hardcoded Assumptions

*   **Memory Limit Not Enforced:** Although the system defines a memory limit, there is currently no mechanism to actively enforce or measure memory usage at runtime.
*   **Security and Sandbox:** Submissions are executed directly on the host using `subprocess.run`.
*   **Single-Language Support:** The judge assumes solvers are Python scripts.
*   **User Experience Gaps:** There is no built-in visualization or graphical feedback for the paths found in the UI.

## Proposed Next-Phase Roadmap

### High-Priority Feature Additions
1.  **Result Visualization Tool:** Implement a visualizer for paths to improve user feedback.
2.  **Standardized Test Suites and Config Schema:** Finalize and document the test suite generation process.
3.  **Expanded Documentation and Templates:** Enhance the participant-facing documentation.

### Submission Flow and CI Improvements
1.  **Enhanced Submission Feedback Loop:** Implement a progress indicator for running jobs.
2.  **Flexible Run Options:** Offer a “quick run” mode for user submissions.
3.  **CI Pipeline Enhancements:** Incorporate integration tests for the web server and automated Docker image builds.
4.  **Grading Robustness:** Implement memory limit enforcement.

### Security, Reproducibility, and Scaling
1.  **Sandboxing and Isolation:** Run each submission in a Docker container or similar isolated environment.
2.  **Credential Management:** Remove hard-coded secrets (like ngrok tokens) from the repository.
3.  **Dependency Pinning for Reproducibility:** Lock exact versions of dependencies.
4.  **Scalability Planning:** Separate the judge execution from the web interface using a job queue.

## Milestones

### Short-Term (1–2 Weeks)
*   Implement basic memory checks.
*   Add a path visualizer on the front-end (web UI).
*   Add progress feedback for submissions.
*   Remove hardcoded secrets and update config.
*   Expand CI tests.

### Mid-Term (1–2 Months)
*   Full sandbox execution for submissions.
*   Job queue system.
*   Scoreboard and account system.
*   Support for additional problem types.
