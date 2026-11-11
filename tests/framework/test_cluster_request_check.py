"""Receipt rejection and local rehearsal; real two-node evidence is separate."""

import multiprocessing
from pathlib import Path

import pytest
from pydantic import ValidationError

from cluster_request_check import (
    ClusterPlan,
    WorkerResult,
    run_worker,
    validate_workers,
)
from cluster_request_scenarios import prepare, publish, verify_snapshots, wait_for
from test_file_request_ledger import join


def plan() -> ClusterPlan:
    return ClusterPlan(jobs=("job-0", "job-1"), nodes=("node-0", "node-1"))


def reports() -> list[WorkerResult]:
    return [
        WorkerResult(
            rank=rank,
            node=f"node-{rank}",
            job_id=f"job-{rank}",
            files={"source.py": "a" * 64},
            source_stable=True,
            outcomes={
                "lock": ("held_until_remote_timeout", "timed_out_then_acquired")[rank],
                "budget": ("reserved", "BudgetExceeded")[rank],
                "dispatch": ("permit", "DispatchAlreadyCommitted")[rank],
                "fence": (
                    "pending_observed_remote_reconciliation",
                    "blocked_then_reconciled_once",
                )[rank],
            },
        )
        for rank in (0, 1)
    ]


def test_verify_normal_receipts() -> None:
    validate_workers(reports(), plan(), {"source.py": "a" * 64})


@pytest.mark.parametrize(
    "field,value",
    [
        ("node", "node-0"),
        ("node", "unplanned-node"),
        ("rank", 0),
        ("job_id", "other"),
        ("files", {}),
        ("source_stable", False),
        ("outcomes", {}),
    ],
)
def test_reject_wrong_identity_source_and_missing_scenarios(
    field: str, value: object
) -> None:
    workers = reports()
    data = workers[1].model_dump(mode="python")
    data[field] = value
    workers[1] = WorkerResult.model_validate(data)
    with pytest.raises(ValueError):
        validate_workers(workers, plan(), {"source.py": "a" * 64})


@pytest.mark.parametrize(
    "phase,value",
    [
        ("budget", "reserved"),
        ("dispatch", "permit"),
        ("lock", "not-checked"),
        ("fence", "not-checked"),
        ("unexpected", "ok"),
    ],
)
def test_reject_extra_scenario_or_unexpected_outcome(phase: str, value: str) -> None:
    workers = reports()
    workers[1].outcomes[phase] = value
    with pytest.raises(ValueError):
        validate_workers(workers, plan(), {"source.py": "a" * 64})


@pytest.mark.parametrize("count", [0, 1, 3])
def test_reject_missing_or_duplicate_workers(count: int) -> None:
    workers = (reports() + reports())[:count]
    with pytest.raises(ValueError):
        validate_workers(workers, plan(), {"source.py": "a" * 64})


@pytest.mark.parametrize(
    "field,value",
    [
        ("rank", True),
        ("rank", 2),
        ("node", ""),
        ("outcomes", []),
        ("source_stable", "true"),
        ("files", {"x": "bad"}),
    ],
)
def test_reject_malformed_worker_data(field: str, value: object) -> None:
    data = reports()[0].model_dump(mode="python")
    data[field] = value
    with pytest.raises(ValidationError):
        WorkerResult.model_validate(data)


def test_coordination_timeout_and_evidence_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    with pytest.raises(TimeoutError):
        wait_for(path, seconds=0.01)
    publish(path, {"original": True})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        publish(path, {"changed": True})
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("jobs", ("same", "same")),
        ("nodes", ("same", "same")),
        ("jobs", ()),
        ("nodes", ("one",)),
        ("jobs", (1, 2)),
        ("nodes", None),
    ],
)
def test_plan_rejects_ambiguous_or_invalid_allocations(
    field: str, value: object
) -> None:
    fields = plan().model_dump(mode="python")
    fields[field] = value
    with pytest.raises(ValidationError):
        ClusterPlan.model_validate(fields)


def test_local_rehearsal_cannot_count_as_cross_node(tmp_path: Path) -> None:
    prepare(tmp_path)
    context = multiprocessing.get_context("spawn")
    workers = [
        context.Process(target=run_worker, args=(tmp_path, rank, "local-fixture"))
        for rank in (0, 1)
    ]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            join(worker)
        verify_snapshots(tmp_path)
        results = [
            WorkerResult.model_validate_json(
                (tmp_path / f"worker-{rank}.json").read_bytes()
            )
            for rank in (0, 1)
        ]
        with pytest.raises(ValueError, match="distinct actual hostnames"):
            validate_workers(results, plan(), dict(results[0].files))
    finally:
        for worker in workers:
            if worker.pid is not None and worker.is_alive():
                worker.kill()
                worker.join(timeout=5)
