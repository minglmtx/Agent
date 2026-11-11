"""Slurm-only cross-node integration driver, separate from storage scenarios.

Rank zero records immutable input hashes and creates fixture grants; each of
two single-node jobs runs one rank. Verification rejects wrong nodes/outcomes, source
drift, or incorrect durable histories. Each failure keeps its full traceback.
Never use this test-only authority or its fabricated grants for paid requests.
"""

import argparse
import hashlib
import json
import os
import socket
import traceback
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from lab_generate_skill.domain.validation import (
    Contract,
    Identifier,
    NonEmptyText,
    Sha256,
)

from cluster_request_scenarios import (
    barrier,
    budget_scenario,
    dispatch_scenario,
    fence_scenario,
    lock_scenario,
    prepare,
    publish,
    verify_snapshots,
    wait_for,
)

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[1]


class WorkerResult(Contract):
    schema_version: Literal["request-ledger-cluster-worker/1"] = (
        "request-ledger-cluster-worker/1"
    )
    rank: int = Field(ge=0, le=1)
    node: NonEmptyText
    job_id: Identifier
    outcomes: dict[str, str]
    files: dict[str, Sha256]
    source_stable: bool


class ClusterPlan(Contract):
    """Exact submitted jobs and nodes; normal partition permits one node/job."""

    schema_version: Literal["request-ledger-cluster-plan/1"] = (
        "request-ledger-cluster-plan/1"
    )
    jobs: tuple[Identifier, Identifier]
    nodes: tuple[Identifier, Identifier]

    @model_validator(mode="after")
    def separate_allocations(self) -> Self:
        if len(set(self.jobs)) != 2 or len(set(self.nodes)) != 2:
            raise ValueError("Two distinct jobs and nodes required")
        return self


def inventory() -> dict[str, str]:
    paths = [ROOT / "pyproject.toml", ROOT / "tools/check_framework.py"]
    paths.extend(sorted((ROOT / "cluster").glob("check*.sbatch")))
    for relative in (
        "src/lab_generate_skill/domain",
        "src/lab_generate_skill/ports",
        "src/lab_generate_skill/adapters",
        "src/lab_generate_skill/runtime",
        "tests/framework",
    ):
        paths.extend(sorted((ROOT / relative).rglob("*.py")))
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def validate_workers(
    workers: list[WorkerResult], plan: ClusterPlan, files: dict[str, str]
) -> None:
    if len(workers) != 2 or {item.rank for item in workers} != {0, 1}:
        raise ValueError("Require exactly two distinct ranks")
    if len({item.node for item in workers}) != 2:
        raise ValueError("Cross-node evidence requires two distinct actual hostnames")
    expected = {
        "lock": ["held_until_remote_timeout", "timed_out_then_acquired"],
        "budget": ["BudgetExceeded", "reserved"],
        "dispatch": ["DispatchAlreadyCommitted", "permit"],
        "fence": [
            "blocked_then_reconciled_once",
            "pending_observed_remote_reconciliation",
        ],
    }
    for worker in workers:
        if (
            worker.job_id != plan.jobs[worker.rank]
            or worker.node != plan.nodes[worker.rank]
            or not worker.source_stable
            or worker.files != files
        ):
            raise ValueError("Worker job/source does not match the frozen check")
        if set(worker.outcomes) != set(expected):
            raise ValueError("Worker did not report every scenario exactly")
    for phase, outcomes in expected.items():
        if sorted(worker.outcomes[phase] for worker in workers) != sorted(outcomes):
            raise ValueError(f"Unexpected {phase} outcomes")


def run_worker(root: Path, rank: int, job_id: str) -> None:
    before = inventory()
    outcomes: dict[str, str] = {}
    for name, scenario in (
        ("lock", lock_scenario),
        ("budget", budget_scenario),
        ("dispatch", dispatch_scenario),
        ("fence", fence_scenario),
    ):
        outcomes[name] = scenario(root, rank)
        barrier(root, name + "-complete", rank)
    after = inventory()
    result = WorkerResult(
        rank=rank,
        node=socket.gethostname(),
        job_id=job_id,
        outcomes=outcomes,
        files=after,
        source_stable=before == after,
    )
    publish(root / f"worker-{rank}.json", result.model_dump(mode="json"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rank", type=int, choices=(0, 1), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    job_id = os.environ.get("SLURM_JOB_ID", "")
    if not job_id:
        parser.error("Compute allocation required")
    root = args.output.resolve()
    if not root.is_relative_to(WORKSPACE) or root == WORKSPACE:
        parser.error("Evidence must stay inside this workspace")
    try:
        wait_for(root / "plan.json", seconds=240)
        plan = ClusterPlan.model_validate_json((root / "plan.json").read_bytes())
        if (
            job_id != plan.jobs[args.rank]
            or socket.gethostname() != plan.nodes[args.rank]
        ):
            raise ValueError("Actual allocation differs from submitted plan")
        if args.rank == 0:
            publish(root / "source-before.json", inventory())
            publish(root / "allocation.json", plan.model_dump(mode="json"))
            prepare(root)
            publish(root / "prepared.json", {"ready": True})
        wait_for(root / "prepared.json", seconds=240)
        if plan != ClusterPlan.model_validate_json(
            (root / "allocation.json").read_bytes()
        ):
            raise ValueError("Prepared allocation differs from worker plan")
        publish(
            root / f"started-{args.rank}.json",
            {"job_id": job_id, "node": socket.gethostname()},
        )
        wait_for(root / f"started-{1-args.rank}.json", seconds=240)
        run_worker(root, args.rank, job_id)
        if args.rank == 0:
            wait_for(root / "worker-1.json")
            files = inventory()
            if files != json.loads((root / "source-before.json").read_text()):
                raise ValueError("Source changed during cross-node check")
            workers = [
                WorkerResult.model_validate_json(
                    (root / f"worker-{rank}.json").read_bytes()
                )
                for rank in (0, 1)
            ]
            validate_workers(workers, plan, files)
            verify_snapshots(root)
            publish(
                root / "result.json",
                {
                    "schema_version": "request-ledger-cluster-check/1",
                    "passed": True,
                    "jobs": list(plan.jobs),
                    "nodes": [item.node for item in workers],
                    "files": files,
                    "source_stable_during_checks": True,
                    "scenarios": list(workers[0].outcomes),
                    "authority": "unit fixture only",
                    "provider_calls": 0,
                    "framework_complete": False,
                },
            )
        else:
            wait_for(root / "result.json")
    except BaseException:
        if root.is_dir():
            path = root / f"failure-rank-{args.rank}.txt"
            with path.open("x") as stream:
                stream.write(traceback.format_exc())
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
