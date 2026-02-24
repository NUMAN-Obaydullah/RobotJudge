"""Determinism gate check — compare two results.json files ignoring runtime-variant fields."""

import hashlib
import json
import copy
import sys
from pathlib import Path


def normalize(data):
    d = copy.deepcopy(data)
    # Remove runtime-variant fields
    for r in d.get("runs", []):
        r.pop("runtime_ms", None)
        r.pop("mem_mb", None)
        r.pop("stdout_path", None)
        r.pop("stderr_path", None)
    for pc in d.get("per_case", []):
        pc.pop("best_runtime_ms", None)
        pc.pop("mean_runtime_ms", None)
        pc.pop("p95_runtime_ms", None)
    d.get("suite", {}).pop("p95_runtime_ms", None)
    d.get("suite", {}).pop("notes", None)
    d.get("suite", {}).pop("suite_score", None)
    return json.dumps(d, sort_keys=True)


if __name__ == "__main__":
    p1 = sys.argv[1] if len(sys.argv) > 1 else "reports/det3/results.json"
    p2 = sys.argv[2] if len(sys.argv) > 2 else "reports/det4/results.json"

    d1 = json.loads(Path(p1).read_text(encoding="utf-8"))
    d2 = json.loads(Path(p2).read_text(encoding="utf-8"))
    h1 = hashlib.sha256(normalize(d1).encode()).hexdigest()
    h2 = hashlib.sha256(normalize(d2).encode()).hexdigest()
    print(f"Run 1 hash: {h1}")
    print(f"Run 2 hash: {h2}")
    if h1 != h2:
        print("ERROR: Results are not deterministic!")
        sys.exit(1)
    print("Determinism gate PASSED")
