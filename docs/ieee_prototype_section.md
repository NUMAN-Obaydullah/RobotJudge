# Section: Evaluation Prototype Implementation

## 1. Prototype Objectives
This prototype implements a minimal end-to-end Robotics Online Judge pipeline to demonstrate the feasibility of automated evaluation workflows. It operationalizes core evaluation requirements (REQ-1 through REQ-6, and partially REQ-7), focusing on establishing a fully automated execution, validation, and metrics aggregation loop. The current iteration utilizes a structured, 2D grid-based robotics proxy domain to isolate and test pathfinding and navigation logic. It is intrinsically designed as a foundational architecture, demonstrating full pipeline evaluation mechanics independent of, yet extensible to, full ROS2 or real-robot physical deployments.

## 2. System Architecture Overview
The system architecture was constructed to be strictly modular, separating submission handling from test generation, execution, and metric validation. 

*   **Problem Registry:** A persistent, versioned schema repository housing the spatial evaluation scenarios. Scenarios are categorized into deterministic difficulty tiers, and the registry actively manages metadata (e.g., optimal path costs, start/goal boundaries) required for validation.
*   **Submission Interface:** The front-facing API handling solver ingress. It securely processes file uploads and enables precise algorithmic configuration, allowing submitters to define target seed ranges and absolute runtime limits (in milliseconds).
*   **Execution Engine:** A headless CI execution module responsible for solver execution. To enforce environmental parity and prevent host-system corruption, solvers are dynamically instantiated within an isolated Docker-based sandbox runner with deterministic processing constraints.
*   **Scenario Generator:** The dynamic environment provisioner. It utilizes controlled pseudo-random seeds combined with tier-based test parameters to systematically instantiate evaluation environments bound to the active solver.
*   **Oracle / Validator:** The independent metric extraction layer. Post-execution, the Oracle verifies the mathematical integrity of the submitted path against collision bounds, computing absolute sequence costs and evaluating adherence to predefined acceptance rules.
*   **Result Store:** The relational data persistence layer. It records high-fidelity per-seed metrics (e.g., execution time, memory footprint, exit codes), calculates aggregated statistical sets, and preserves historical evaluation vectors.
*   **Dashboard:** The synchronous visualization telemetry. It translates the raw Result Store data into operational insights, prominently displaying overall failure rates, Mean Cost, and P95 runtimes alongside granular per-seed breakdowns.

## 3. Execution Pipeline
The evaluation lifecycle follows a continuous integration (CI) paradigm, triggered via solver submission and executed headlessly:
1.  **Ingress:** A submission payload alongside evaluation configurations (time bounds, seed iteration range) is posted to the Job system.
2.  **Environment Provisioning:** The Execution Engine allocates a secure, ephemeral Docker container equipped with isolated compute boundaries.
3.  **Iterative Invocation:** The engine iterates sequentially through the predefined seed set.
4.  **Execution (Per-Seed):**
    *   The Scenario Generator provisions the distinct environment parameters dictated by the respective seed.
    *   The untrusted solver executable is invoked against the scenario.
    *   Raw performance indicators (peak memory, time-to-completion, exit status) are simultaneously collected by the Execution Engine. 
5.  **Validation:** Upon natural termination or forced timeout, the Oracle evaluates the generated output log, assigning heuristic penalties and extracting absolute cost metrics.
6.  **Aggregation:** Data vectors across all simulated seeds are consolidated. Statistical measurements, such as the suite success rate and 95th-percentile (P95) runtime, are computationally derived.
7.  **Final Verdict:** The aggregate metrics are evaluated against success gates to compute an absolute mathematical verdict (e.g., PASS, FAIL, TIME LIMIT EXCEEDED). 
8.  **Persistence:** Results are historically logged in the Result Store and instantly routed to the Dashboard via API polling. 

Determinism is strictly enforced throughout the pipeline via hardcoded spatial seeds and hermetic container environments. Failures (computational crashes, memory overflow, routing impossibilities) are immediately captured as standard errors but do not halt the execution workflow; the failed seed is marked and penalized in the aggregation mathematics, while the subsequent seeds continue to evaluate.

## 4. Requirement Coverage Mapping
The current prototype architecture successfully operationalizes the mandated pipeline components mapped below:

*   **REQ-1 (Container-first execution):** Submissions do not execute natively. The Execution Engine relies inherently on Docker to provide secure, ephemeral containment isolation. Compute resources (CPUs, Memory) are capped at the container level to enforce deterministic allocation.
*   **REQ-2 (Seed governance):** The system completely abstracts seed management from the user script. The Submission Interface dictates exact iteration boundaries, and the Result Store produces explicit per-seed breakdown tables evaluating variance across states.
*   **REQ-3 (Scenario–Oracle separation):** The environment formulation (Scenario Generator) operates independently of path verification (Oracle). The solver's heuristic output is mathematically analyzed against spatial boundaries without relying on the generator pipeline for truth computation.
*   **REQ-4 (Statistical verdicts):** Success is not based on anecdotal iterations. The Aggregation engine mathematically computes holistic performance logic, generating cross-seed success rates and 95th-percentile (P95) operational metrics.
*   **REQ-5 (Artifact traceability):** The Result Store retains permanent, schema-level tracking of all submission attempts. High-fidelity logs, JSON paths, and exact metric derivations are stored historically for full traceability and independent re-verification.
*   **REQ-6 (Resource/time constraints):** Maximum allocated runtime is strictly tracked via `psutil` integration against wall-clock parameters. Unresponsive or divergent scripts are aggressively halted upon limit breaches to prevent hardware monopolization.
*   **REQ-7 (Safety constraints):** Current implementations proactively enforce strict physical boundary checks including grid collision states and kinematic safety bounds. The Oracle mathematically prohibits impossible maneuvers (e.g., instantaneous 180-degree phase reversals indicative of infinite angular acceleration) to ensure validated trajectories remain physically executable.

**Requirement Verification Matrix**

| Requirement                           | Supported | Implementation Evidence                                                                           |
| ------------------------------------- | --------- | ------------------------------------------------------------------------------------------------- |
| **REQ-1** (Container-first execution) | Yes       | Headless Docker Runner (`rj-sandbox`) utilizing resource constraints.                              |
| **REQ-2** (Seed governance)           | Yes       | Configurable seed iterations and precise tabular breakdowns per seed limit.                       |
| **REQ-3** (Scenario–Oracle separated) | Yes       | Distinct pipeline boundaries exist separating the generator script logic from the mathematical validator.            |
| **REQ-4** (Statistical verdicts)      | Yes       | Automatic mathematical derivations including Suite Success Rates and explicit aggregated P95 execution runtimes. |
| **REQ-5** (Artifact traceability)     | Yes       | Comprehensive persistence schema retaining persistent database traces and path artifacts.             |
| **REQ-6** (Resource/time constraints) | Yes       | Synchronous millisecond-accurate runtime recording and explicit timeout halting mechanisms.         |
| **REQ-7** (Safety constraints)        | Yes       | Active penalty matrices preventing collision occurrences and enforcing kinematic angular restrictions. |

## 5. Limitations and Roadmap
The present evaluation infrastructure successfully validates the foundational components of the Robotics Online Judge architecture; however, several design simplifications exist in the current prototype iteration:

*   **Algorithmic Proxy Limitations:** The domain is currently simplified to evaluate logic via a 2D structured grid representation instead of complex 3D kinematic environments.
*   **Missing Intermediate Layer:** There is currently no active, generalized ROS2 message-proxy adapter for translating baseline signals between the judge and external robotic software.
*   **Physical Deployment:** The architecture is a pure simulation engine; it lacks direct integration pipelines with real-world physical robot hardware endpoints.
*   **Safety Dynamics:** Safety enforcement is limited strictly to spatial coordinate validation (obstacle collisions), omitting dynamic momentum or sensory limitations constraints.
*   **Scalability Profile:** Parallel load-balancing and extreme concurrency scaling have not been comprehensively mapped or verified.

**Development Roadmap:**
To directly address these technical gaps and achieve full-spectrum maturity, successive development sprints are structured to prioritize:
1.  **ROS2 Adapter Layer:** The introduction of a dedicated communication bridging layer to interpret standardized real-time robotics telemetry payloads natively.
2.  **Webots / Gazebo Integration:** Transitioning the scenario generation and Oracle parameters from 2D coordinates to full 3D physics engine orchestrations.
3.  **Real-Robot Tiering:** Establishing secure on-site proxy runners that interface directly with physical test environments following cloud-verified simulation successes.
4.  **Hardware Constraint Module:** Upgrading the Oracle logic to comprehensively measure momentum, force execution, and sensor failure likelihoods as distinct safety violation parameters.
