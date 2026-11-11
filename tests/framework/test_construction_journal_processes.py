"""New OS processes share files only; unit authority is explicit, no models."""

import multiprocessing
import os
from pathlib import Path
from multiprocessing.process import BaseProcess

from pydantic import TypeAdapter

from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.construction import ConstructionPlan, ProgressEvent
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import RevisionConflict

from construction_storage_fixtures import (
    fixture,
    StorageFixture,
    UnitConstructionAuthority,
)
from claim_fixtures import UnitClaimAuthority
from test_run_journal import command
from context_storage_fixtures import UnitContextAuthority
from test_retrieval_evidence import UnitAuthority as UnitRetrievalAuthority


def reopen(root: Path, plan_json: str) -> StorageFixture:
    store = FileEvidenceStore(root / "evidence")
    return StorageFixture(
        root,
        store,
        ConstructionPlan.model_validate_json(plan_json),
        UnitConstructionAuthority(store),
        UnitContextAuthority(),
        UnitRetrievalAuthority(store),
        UnitClaimAuthority(),
    )


def append_worker(
    root: Path, plan_json: str, event_json: str, output: Path, crash: bool = False
) -> None:
    data = reopen(root, plan_json)
    event: ProgressEvent = TypeAdapter(ProgressEvent).validate_json(event_json)
    try:
        data.journal().append(event, -1, event.operation)
        if crash:
            os._exit(23)
        output.write_text("committed")
    except RevisionConflict:
        output.write_text("stale")


def read_worker(root: Path, plan_json: str, output: Path) -> None:
    data = reopen(root, plan_json)
    progress = data.journal().read(command())
    output.write_text(progress.model_dump_json())


def join(worker: BaseProcess, expected: int = 0) -> None:
    worker.join(25)
    if worker.is_alive():
        worker.kill()
        worker.join(5)
    assert worker.exitcode == expected


def test_two_processes_same_revision_only_one_commits(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    progress = data.journal().create(data.plan, command())
    events = [data.event(progress, request_suffix=f"-{i}") for i in range(2)]
    ctx = multiprocessing.get_context("spawn")
    workers = [
        ctx.Process(
            target=append_worker,
            args=(
                tmp_path,
                data.plan.model_dump_json(),
                event.model_dump_json(),
                tmp_path / f"worker-{i}",
            ),
        )
        for i, event in enumerate(events)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        join(worker)
    assert sorted((tmp_path / f"worker-{i}").read_text() for i in range(2)) == [
        "committed",
        "stale",
    ]
    stored = data.journal().read(command())
    assert len(stored.events) == 1 and stored.events[0] in events


def test_crash_after_call_registration_new_process_retains_pending_identity(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    progress = data.journal().create(data.plan, command())
    event = data.event(progress)
    ctx = multiprocessing.get_context("spawn")
    plan_json = data.plan.model_dump_json()
    writer = ctx.Process(
        target=append_worker,
        args=(tmp_path, plan_json, event.model_dump_json(), tmp_path / "unused", True),
    )
    writer.start()
    join(writer, 23)
    reader = ctx.Process(
        target=read_worker, args=(tmp_path, plan_json, tmp_path / "recovered.json")
    )
    reader.start()
    join(reader)
    recovered = ConstructionProgress.model_validate_json(
        (tmp_path / "recovered.json").read_bytes()
    )
    assert recovered.events == (event,)
    assert recovered.project().next_action.kind == "await_response"
    assert recovered.project().pending_call is not None
    assert writer.pid != reader.pid
