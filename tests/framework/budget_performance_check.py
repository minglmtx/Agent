"""Bounded compute-only capacity comparison and actual workspace transactions."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from budget_capacity_fixtures import snapshot
from budget_capacity_reference import reference_capacity
from budget_performance_transaction import measure_transactions

PROJECT = Path(__file__).resolve().parents[2]


def inventory() -> dict[str, str]:
    roots = (
        PROJECT / "src/lab_generate_skill/domain",
        PROJECT / "src/lab_generate_skill/adapters",
        PROJECT / "src/lab_generate_skill/ports",
        PROJECT / "src/lab_generate_skill/runtime",
        PROJECT / "tests/framework",
    )
    return {
        str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for root in roots
        for p in sorted(root.rglob("*.py"))
    }


def run_one(count: int, root: Path) -> dict[str, object]:
    value = snapshot(count)
    optimized: list[float] = []
    reference: list[float] = []
    for _ in range(2):
        start = perf_counter()
        value.check_capacity()
        optimized.append(perf_counter() - start)
        if count <= 128:
            start = perf_counter()
            reference_capacity(value)
            reference.append(perf_counter() - start)
    return {
        "requests": count,
        "snapshot_bytes": len(value.model_dump_json().encode()),
        "optimized_capacity_seconds": optimized,
        "reference_capacity_seconds": reference,
        "reference_scope": "retained prefix algorithm using current shared state replay; not old-release transaction timing",
        "transactions": measure_transactions(root, count),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, choices=(32, 64, 128, 256))
    args = parser.parse_args()
    if not os.environ.get("SLURM_JOB_ID"):
        parser.error("Slurm compute allocation required")
    output = args.output.resolve()
    experiment_root = PROJECT.parents[1] / "experiments"
    if not output.is_relative_to(experiment_root) or output == experiment_root:
        parser.error("Output must be a new workspace experiments directory")
    if args.count is not None:
        print(json.dumps(run_one(args.count, output)), flush=True)
        return 0
    output.mkdir(exist_ok=False)
    before = inventory()
    rows: list[object] = []
    passed = True
    for count in (32, 64, 128, 256):
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(Path(__file__).resolve()),
                    "--output",
                    str(output / ("ledger-" + str(count))),
                    "--count",
                    str(count),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            (output / (str(count) + ".stdout")).write_text(result.stdout)
            (output / (str(count) + ".stderr")).write_text(result.stderr)
            if result.returncode != 0:
                passed = False
                rows.append({"requests": count, "returncode": result.returncode})
                break
            rows.append(json.loads(result.stdout))
        except subprocess.TimeoutExpired:
            passed = False
            rows.append({"requests": count, "timeout_seconds": 180})
            break
    stable = before == inventory()
    report = {
        "job_id": os.environ["SLURM_JOB_ID"],
        "node": os.uname().nodename,
        "passed": passed and stable,
        "source_files": before,
        "source_stable": stable,
        "rows": rows,
        "authority": "explicit synthetic unit authority; no provider calls",
        "not_production_throughput": True,
        "full_regression_run": False,
    }
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "output": str(output)}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
