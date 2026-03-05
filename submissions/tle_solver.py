#!/usr/bin/env python3
"""TLE Solver for RobotJudge-CI.

This solver intentionally sleeps for 15 seconds on every execution
to guarantee a Time Limit Exceeded (TLE) verdict across all testcases.

Usage:
    python tle_solver.py --case <case.json> --seed <int> --out <path.json>
"""

import argparse
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    # Sleep well beyond the standard 2000-5000ms timeout
    time.sleep(15)

    # We will never reach this point because the Docker async engine
    # will SIGKILL this process due to the timeout.
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write('{"status": "no_path", "path": []}')

if __name__ == "__main__":
    main()
