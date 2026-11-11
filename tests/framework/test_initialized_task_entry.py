"""Frozen initialized inputs on real journals/claims, with unit physical/model effects.

No source, preparation or initialization producer is executed. These software
checks do not authorize a closed historical run or establish website results.
"""

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator
import pytest
from lab_generate_skill.application.initialized_task_entry import (
    execute_initialized_task,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.application.task_execution_events import TaskExecutionEvents
from lab_generate_skill.bootstrap.execution_task import RecordedExecutionTask
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.run_journal import RunEntry
from lab_generate_skill.domain.execution import RunEvent
from construction_storage_fixtures import put
from execution_task_fixtures import execution_case
from task_execution_fixtures import task_case


def frozen_prefix(c: Any) -> tuple[EvidenceRef, int]:
    """Construct only a typed unit frozen handoff, not the upstream producers."""
    snapshot = c.deps.runs.read(c.plan.read_operation)
    events = TaskExecutionEvents(
        c.plan,
        c.deps.runs,
        c.deps.evidence,
        c.deps.controls,
        c.deps.clock,
        snapshot,
        c.deps.source,
    )
    p = events.put("plan", c.plan, c.plan.operation)
    events.append("planned", events.operation("planned"), (p,))
    for stage in ("acquiring", "preparing", "starting"):
        events.append(stage, events.operation(stage), (c.plan.declaration_ref,))
    initialized = c.phases.initialized
    ref = events.put("initialized", initialized, events.operation("starting-body"))
    events.append(
        "baseline_verified",
        events.operation("baseline"),
        (initialized.baseline_ref, initialized.equivalence_ref),
    )
    return ref, events.snapshot.revision


def forbid_prefix(c: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Frozen initialized consumer called upstream producer")

    for method in ("acquire", "prepare", "start"):
        monkeypatch.setattr(c.phases, method, forbidden)


@contextmanager
def bounded_owner(events: list[str]) -> Iterator[None]:
    events.append("enter-current-owner")
    try:
        yield
    finally:
        events.append("bounded-current-owner-close")


@pytest.mark.parametrize("kind", ["execution", "construction"])
def test_frozen_initialized_tail_consumes_once_without_upstream_and_keeps_valid_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    c = (execution_case if kind == "execution" else task_case)(tmp_path / kind)
    ref, revision = frozen_prefix(c)
    before = c.deps.runs.read(c.plan.read_operation)
    forbid_prefix(c, monkeypatch)
    result = execute_initialized_task(c.plan, c.deps, ref, expected_revision=revision)
    assert result.evaluation.status == "failure"
    assert c.model.calls == c.browser.calls == 1
    assert c.phases.calls == [
        "preflight",
        "bind_actor",
        "model",
        "browser",
        "capture",
        "evaluate",
        "close",
        "verify_closed",
        "restore",
    ]
    after = c.deps.runs.read(c.plan.read_operation)
    assert after.entries[: len(before.entries)] == before.entries
    assert after.project()[1][0].stage == "sealed"
    calls = list(c.phases.calls)
    with pytest.raises((InvalidTransition, RevisionConflict)):
        execute_initialized_task(c.plan, c.deps, ref, expected_revision=revision)
    assert c.phases.calls == calls and c.model.calls == 1


@pytest.mark.parametrize("fault", ["schema", "revision", "plan", "binding", "baseline"])
def test_wrong_frozen_handoff_refuses_before_actor_and_preserves_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = execution_case(tmp_path / fault)
    ref, revision = frozen_prefix(c)
    before = c.deps.runs.read(c.plan.read_operation)
    forbid_prefix(c, monkeypatch)
    plan = c.plan
    if fault == "schema":
        ref = ref.model_copy(update={"content_schema": "wrong/1"})
    elif fault == "revision":
        revision += 1
    elif fault == "plan":
        plan = plan.model_copy(update={"cleanup_seconds": plan.cleanup_seconds + 1})
    else:
        initialized = c.phases.initialized
        if fault == "binding":
            initialized = initialized.model_copy(
                update={
                    "actor": initialized.actor.model_copy(
                        update={
                            "operation": initialized.actor.operation.model_copy(
                                update={"operation_id": "foreign"}
                            )
                        }
                    )
                }
            )
        else:
            initialized = initialized.model_copy(
                update={"baseline_ref": initialized.equivalence_ref}
            )
        ref = put(c.source.data.store, initialized, "initialized-task/1")
    with pytest.raises(
        (ValueError, InvalidTransition, OwnershipConflict, RevisionConflict)
    ):
        execute_initialized_task(plan, c.deps, ref, expected_revision=revision)
    assert c.deps.runs.read(c.plan.read_operation) == before
    assert c.model.calls == c.browser.calls == 0


def test_stopped_original_run_is_not_revived_by_frozen_initialization(
    tmp_path: Path,
) -> None:
    c = execution_case(tmp_path / "stopped")
    ref, revision = frozen_prefix(c)
    snap = c.deps.runs.read(c.plan.read_operation)
    op = c.plan.read_operation.cleanup(
        "cancel-original", now=c.deps.clock.utcnow(), seconds=30
    )
    entry = RunEntry(
        event=RunEvent(
            stage="closing",
            operation=op,
            previous_operation_id=snap.project()[0].events[-1].operation.operation_id,
            occurred_at=c.deps.clock.utcnow(),
            component_id="unit-original-owner",
            stop_reason="cancelled",
            outputs=(ref,),
        )
    )
    current = c.deps.runs.append(entry, revision, op)
    with pytest.raises(InvalidTransition):
        execute_initialized_task(
            c.plan, c.deps, ref, expected_revision=current.revision
        )
    assert c.deps.runs.read(c.plan.read_operation) == current
    assert c.model.calls == c.browser.calls == 0


def test_current_claim_revocation_closes_owner_scope_without_replacing_original_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = execution_case(tmp_path / "claim")
    ref, revision = frozen_prefix(c)
    forbid_prefix(c, monkeypatch)
    original = PermissionError("original claim revoked")

    def denied(*args: Any, **kwargs: Any) -> Any:
        raise original

    monkeypatch.setattr(c.deps.claims, "require", denied)
    owner: list[str] = []
    task = RecordedExecutionTask(
        c.plan, c.deps, resource_scope=lambda: bounded_owner(owner)
    )
    before = c.deps.runs.read(c.plan.read_operation)
    with pytest.raises(PermissionError) as caught:
        task.execute_initialized(
            c.plan.intent, c.plan.operation, ref, expected_revision=revision
        )
    assert caught.value is original
    assert owner == ["enter-current-owner", "bounded-current-owner-close"]
    assert c.model.calls == c.browser.calls == 0
    assert c.deps.runs.read(c.plan.read_operation) == before


@pytest.mark.parametrize("phase", ["model", "capture", "evaluate"])
def test_tail_failure_retains_partial_trace_and_runs_original_close_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    c = execution_case(tmp_path / phase)
    ref, revision = frozen_prefix(c)
    forbid_prefix(c, monkeypatch)
    failure = OSError("original " + phase)
    c.phases.errors[phase] = failure
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_initialized_task(c.plan, c.deps, ref, expected_revision=revision)
    error = caught.value
    assert error.trace is not None and "trace_snapshot" in error.known
    assert error.primary is failure if phase != "model" else error.primary is not None
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    assert "reset" in error.known and not error.cleanup_errors


def test_unknown_close_keeps_business_failure_and_never_restores(
    tmp_path: Path,
) -> None:
    c = execution_case(tmp_path / "close")
    ref, revision = frozen_prefix(c)
    failure = TimeoutError("native close unknown")
    c.phases.errors["close"] = failure
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_initialized_task(c.plan, c.deps, ref, expected_revision=revision)
    assert caught.value.evaluation is not None
    assert caught.value.evaluation.status == "failure"
    assert failure in caught.value.cleanup_errors
    assert "restore" not in c.phases.calls and "reset" not in caught.value.known


def test_executing_commit_lost_ack_never_dispatches_and_owner_closes_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = execution_case(tmp_path / "lost-ack")
    ref, revision = frozen_prefix(c)
    forbid_prefix(c, monkeypatch)
    original = c.deps.runs.append
    lost = OSError("executing commit acknowledgement lost")

    def append(entry: Any, expected: int, operation: Any) -> Any:
        result = original(entry, expected, operation)
        if entry.kind == "attempt" and entry.event.stage == "executing":
            raise lost
        return result

    monkeypatch.setattr(c.deps.runs, "append", append)
    owner: list[str] = []
    task = RecordedExecutionTask(
        c.plan, c.deps, resource_scope=lambda: bounded_owner(owner)
    )
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        task.execute_initialized(
            c.plan.intent, c.plan.operation, ref, expected_revision=revision
        )
    assert caught.value.primary is lost
    assert owner == ["enter-current-owner", "bounded-current-owner-close"]
    assert c.model.calls == c.browser.calls == 0 and "restore" not in c.phases.calls
    snap = c.deps.runs.read(c.plan.read_operation)
    assert snap.project()[1][0].stage == "executing"
    with pytest.raises(InvalidTransition):
        task.execute_initialized(
            c.plan.intent, c.plan.operation, ref, expected_revision=snap.revision
        )
    assert c.model.calls == 0 and c.deps.runs.read(c.plan.read_operation) == snap


def test_initialized_bootstrap_requires_explicit_bounded_original_owner(
    tmp_path: Path,
) -> None:
    c = execution_case(tmp_path / "missing-owner")
    ref, revision = frozen_prefix(c)
    task = RecordedExecutionTask(c.plan, c.deps)
    with pytest.raises(ValueError, match="resource-owner"):
        task.execute_initialized(
            c.plan.intent, c.plan.operation, ref, expected_revision=revision
        )
    assert not c.phases.calls and c.model.calls == c.browser.calls == 0
