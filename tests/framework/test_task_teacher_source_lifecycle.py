"""Original run closure and unresolved-call guards for persisted task sources.

The fixture executes current Actor2 with a declared unit engine. No physical
website, actual weights, provider permission or new attempt is created here.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.teacher_source import (
    publish_teacher_source,
    TeacherSourceUnconfirmed,
)
from lab_generate_skill.application.teacher_source_review import review_teacher_source
from lab_generate_skill.application.task_teacher_source import (
    CompletedTaskTeacherSourceAuthority,
)
from lab_generate_skill.domain.construction import CallPlanned, CallUncertain
from lab_generate_skill.domain.execution import RunStage
from lab_generate_skill.domain.errors import OperationStopped
from construction_storage_fixtures import put
from task_teacher_source_fixtures import complete_task_source_case
from test_task_teacher_source_boundaries import read_deps
from test_run_journal import Harness, CancelSwitch, command


def test_task_source_full_run_sealed_read_uses_original_parent_and_no_new_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = complete_task_source_case(tmp_path / "case", monkeypatch, source_seconds=180)
    first = c.tasks[0].task
    controls = first.deps.controls
    op = c.bindings.operation
    source = publish_teacher_source(
        c.progress, c.bindings, c.deps(), control=controls.bind(op)
    )
    c.native.client.close(controls.bind(op))
    before = first.deps.runs.read(op)
    snapshot = before
    run_plan = c.original_source.plans.load(c.data.plan.run, op)
    harness = Harness(
        c.data.root,
        c.data.store,
        first.deps.runs,
        c.data.plan.run,
        c.data.plan.claim_ref,
        CancelSwitch(),
        run_plan.run_capacity,
    )
    for stage in ("closing", "sealed"):
        event = harness.run_entry(snapshot, cast(RunStage, stage))
        snapshot = first.deps.runs.append(
            event, snapshot.revision, event.event.operation
        )
    closed = op.cleanup(
        "task-source-sealed-read", now=datetime.now(timezone.utc), seconds=60
    )
    calls = c.native.loader.session.calls
    receipt = review_teacher_source(
        source, read_deps(c, closed), control=controls.bind(closed)
    )
    assert receipt.bindings == c.bindings
    assert snapshot.project()[0].stage == "sealed"
    assert snapshot.entries[: len(before.entries)] == before.entries
    assert c.native.loader.session.calls == calls == 4
    assert c.data.journal().read(closed) == c.progress
    # A recorded source can be read; a new source cannot be prepared after closure.
    with pytest.raises(TeacherSourceUnconfirmed) as caught:
        publish_teacher_source(
            c.progress, c.bindings, c.deps(), control=controls.bind(op)
        )
    assert caught.value.phase == "authority" and not caught.value.retained
    assert first.deps.runs.read(closed) == snapshot


@pytest.mark.parametrize("state", ["pending", "unknown"])
def test_original_unresolved_teacher_call_cannot_be_bypassed_by_new_source_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    c = complete_task_source_case(tmp_path / "case", monkeypatch, source_seconds=180)
    controls = c.tasks[0].task.deps.controls
    journal = c.data.journal()
    event = c.data.event(c.progress)
    assert isinstance(event, CallPlanned)
    current = journal.append(event, c.progress.revision, event.operation)
    if state == "unknown":
        ref = put(c.data.store, {"unknown_request": event.call.request_id})
        uncertain = CallUncertain(
            operation=command("task-source-original-unknown"),
            request_id=event.call.request_id,
            evidence_ref=ref,
        )
        current = journal.append(uncertain, current.revision, uncertain.operation)
    changed = c.bindings.model_copy(
        update={"request_id": "new-id-does-not-authorize-replay"}
    )
    before = c.tasks[0].task.deps.runs.read(c.bindings.operation)
    calls = c.native.loader.session.calls
    with pytest.raises(TeacherSourceUnconfirmed) as caught:
        publish_teacher_source(
            c.progress, changed, c.deps(), control=controls.bind(c.bindings.operation)
        )
    assert caught.value.phase == "authority" and not caught.value.retained
    assert journal.read(c.bindings.operation) == current
    assert c.tasks[0].task.deps.runs.read(c.bindings.operation) == before
    assert c.native.loader.session.calls == calls == 4
    c.native.client.close(controls.bind(c.bindings.operation))


def test_task_source_dependency_role_and_timeout_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = complete_task_source_case(tmp_path / "case", monkeypatch, source_seconds=180)
    good = c.authority(c.bindings.operation)
    values = [good.original, c.review, c.original_source.contexts, c.bindings.operation]
    bad_inputs: tuple[Any, ...] = (None, {}, [], "", True)
    for position in range(4):
        for bad in bad_inputs:
            changed: list[Any] = list(values)
            changed[position] = bad
            with pytest.raises((ValueError, ValidationError)):
                CompletedTaskTeacherSourceAuthority(*changed)
    control = c.tasks[0].task.deps.controls.bind(c.bindings.operation)
    error = OperationStopped("DEADLINE_EXCEEDED", "original-task-source-timeout")

    def timeout() -> float:
        raise error

    calls = c.native.loader.session.calls
    with monkeypatch.context() as patch:
        patch.setattr(control, "checkpoint", timeout)
        with pytest.raises(TeacherSourceUnconfirmed) as caught:
            publish_teacher_source(c.progress, c.bindings, c.deps(), control=control)
    assert caught.value.primary is error and not caught.value.retained
    assert c.native.loader.session.calls == calls == 4
    c.native.client.close(c.tasks[0].task.deps.controls.bind(c.bindings.operation))
