"""No unknown replay, cleanup ordering and original result/identity boundaries."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionDeps,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.application.actor_generation import ActorDispatchFailure
from lab_generate_skill.application.browser_action import BrowserDispatchFailure
from lab_generate_skill.application.construct_targets import construct_targets
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OperationStopped,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    InitializedTask,
    TaskCaptureResult,
)
from lab_generate_skill.domain.run_journal import JournalEntry, RunSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRequirements
from lab_generate_skill.domain.task_execution_result import TaskFailureContext
from lab_generate_skill.ports.task_execution import TaskActorBinding
from task_execution_fixtures import task_case
from task_execution_construction_fixtures import construction_task_case
from test_run_journal import command


def test_original_construction_calls_complete_task_adapter_and_verifies_native_result(
    tmp_path: Path,
) -> None:
    c, step, deps = construction_task_case(tmp_path / "construction")
    result = construct_targets(step, deps)
    view = result.progress.project()
    assert (
        result.status == "advanced"
        and view.next_action.kind == "execute"
        and view.next_action.candidate_slot == 1
    )
    assert len(view.attempts) == 1 and view.attempts[0].evaluation.status == "failure"
    assert c.model.calls == c.browser.calls == c.actor.calls == 1
    with pytest.raises(RevisionConflict):
        construct_targets(step, deps)
    assert c.phases.calls.count("acquire") == c.phases.calls.count("restore") == 1


@pytest.mark.parametrize(
    "phase", ["acquire", "prepare", "start", "model", "browser", "capture", "evaluate"]
)
def test_partial_execution_keeps_original_error_and_finally_closes_and_resets_without_replay(
    tmp_path: Path, phase: str
) -> None:
    c = task_case(tmp_path / phase)
    original = OSError("original " + phase + " partial failure")
    c.phases.errors[phase] = original
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    error = caught.value
    if phase in ("model", "browser"):
        assert isinstance(error.primary, ActorLoopFailure)
        dispatch = error.primary.primary
        assert isinstance(dispatch, (ActorDispatchFailure, BrowserDispatchFailure))
        assert (
            isinstance(dispatch, ActorDispatchFailure)
            if phase == "model"
            else isinstance(dispatch, BrowserDispatchFailure)
        )
        assert dispatch.primary is original and dispatch.__cause__ is original
        assert dispatch.phase == ("generate" if phase == "model" else "step")
        assert error.trace is not None and "trace_snapshot" in error.known
    else:
        assert error.primary is original
    assert not error.cleanup_errors and "reset" in error.known
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    before = list(c.phases.calls)
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(c.plan, c.deps)
    assert c.phases.calls == before
    assert c.deps.runs.read(command()).project()[1][0].stage == "sealed"


@pytest.mark.parametrize("phase", ["close", "verify_closed", "restore"])
def test_unconfirmed_close_never_restores_and_restore_failure_never_returns_completed_task(
    tmp_path: Path, phase: str
) -> None:
    c = task_case(tmp_path / phase)
    original = TimeoutError("original " + phase + " outcome unknown")
    c.phases.errors[phase] = original
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    error = caught.value
    assert error.primary is None and original in error.cleanup_errors
    assert "reset" not in error.known
    assert ("restore" in c.phases.calls) == (phase == "restore")
    assert error.evaluation is not None and error.evaluation.status == "failure"
    assert (
        c.deps.runs.read(command()).project()[1][0].stage == "sealed"
    ), error.cleanup_errors
    assert c.model.calls == c.browser.calls == 1
    snapshot = c.deps.runs.read(command())
    assert all(
        len(entry.model_dump_json().encode()) <= snapshot.capacity.max_entry_bytes
        for entry in snapshot.entries
    )
    # Complete original associations survive in CAS instead of duplicate inline
    # journal references; no raw facts are cut to make diagnostics fit.
    failure = next(
        event.cleanup_errors[0]
        for event in snapshot.project()[1][0].events
        if event.cleanup_errors
    )
    assert len(failure.evidence) == 1
    context = TaskFailureContext.model_validate_json(
        c.admission.data.store.read(failure.evidence[0])
    )
    assert context.intent == c.plan.intent
    assert error.known["trace"] in context.references
    assert error.known["evaluation"] in context.references


def test_execution_and_cleanup_errors_remain_separate_and_no_restore_on_unknown_closure(
    tmp_path: Path,
) -> None:
    c = task_case(tmp_path / "combined")
    original = OperationStopped("CANCELLED", c.plan.operation.operation_id)
    closing = OSError("original resource close unconfirmed")
    c.phases.errors.update(prepare=original, close=closing)
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    error = caught.value
    assert error.primary is original and error.__cause__ is original
    assert closing in error.cleanup_errors and "restore" not in c.phases.calls
    diagnostic = describe_error(error)
    assert (
        diagnostic.cause is not None
        and diagnostic.cause.type_name == "OperationStopped"
    )
    assert [child.type_name for child in diagnostic.children] == ["OSError"]
    assert "original resource close unconfirmed" not in diagnostic.model_dump_json()
    assert c.actor.calls == c.model.calls == c.browser.calls == 0
    attempt = c.deps.runs.read(command()).project()[1][0]
    assert attempt.stage == "sealed" and attempt.stop_reason == "cancelled"


@pytest.mark.parametrize("fault", ["none", "receipt", "permission"])
def test_completed_close_metadata_failure_uses_original_receipt_and_fresh_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = task_case(tmp_path / fault)
    original_close = c.phases.close
    original_verify = c.deps.authority.verify_closed
    checks = []

    class LateCloseMetadataFailure(RuntimeError):
        pass

    def close(*args: Any, **kwargs: Any) -> Any:
        closed = original_close(*args, **kwargs)
        if fault == "receipt":
            closed = closed.model_copy(
                update={"closure_refs": (c.plan.reset_plan_ref,)}
            )
        error = LateCloseMetadataFailure("unit completed physical close")
        error.known_closed = closed  # type: ignore[attr-defined]
        raise error

    def verify(*args: Any, **kwargs: Any) -> None:
        checks.append(args[2].operation_id)
        if fault == "permission":
            raise PermissionError("unit original cleanup permission revoked")
        original_verify(*args, **kwargs)

    monkeypatch.setattr(c.phases, "close", close)
    monkeypatch.setattr(c.deps.authority, "verify_closed", verify)
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    error = caught.value
    assert error.primary is None
    assert any(isinstance(e, LateCloseMetadataFailure) for e in error.cleanup_errors)
    assert c.phases.calls.count("close") == 1
    if fault == "none":
        assert c.phases.calls.count("restore") == 1 and "reset" in error.known
        assert checks and all(name.endswith("restoring") for name in checks)
    else:
        assert "restore" not in c.phases.calls and "reset" not in error.known
        if fault == "receipt":
            assert checks == []


@pytest.mark.parametrize(
    "fault", ["source", "preflight", "expired", "missing_actors", "initial_skill"]
)
def test_admission_and_initial_view_faults_cannot_enter_actor(
    tmp_path: Path, fault: str
) -> None:
    c = task_case(tmp_path / fault)
    deps = c.deps
    plan = c.plan
    if fault == "source":
        c.phases.denied = True
    elif fault == "preflight":
        c.phases.errors["preflight"] = ValueError("original capture unavailable")
    elif fault == "expired":
        plan = TaskExecutionPlan.model_validate(
            plan.model_copy(
                update={
                    "operation": plan.operation.model_copy(
                        update={
                            "deadline": datetime.now(timezone.utc)
                            - timedelta(seconds=1)
                        }
                    )
                }
            )
        )
    elif fault == "missing_actors":
        deps = replace(deps, actors=cast(TaskActorBinding, None))
    else:
        initial = c.phases.initialized
        actor = initial.actor.model_copy(
            update={
                "skill": initial.actor.skill.model_copy(
                    update={"title": "changed original skill"}
                )
            }
        )
        c.phases.initialized = InitializedTask.model_validate(
            initial.model_copy(update={"actor": actor})
        )
    with pytest.raises(
        (PermissionError, ValueError, OperationStopped, TaskExecutionUnconfirmed)
    ):
        execute_task(plan, deps)
    assert c.actor.calls == c.model.calls == c.browser.calls == 0
    assert ("close" in c.phases.calls) == (fault == "initial_skill")


@pytest.mark.parametrize("status", ["success", "unknown"])
def test_original_evaluation_status_is_not_changed_by_actor_or_cleanup(
    tmp_path: Path, status: str
) -> None:
    c = task_case(tmp_path / status)
    c.phases.evaluation_status = status
    result = execute_task(c.plan, c.deps)
    assert result.evaluation.status == status
    assert result.evaluation.reward == ({"success": 1, "unknown": None}[status])
    assert c.model.calls == c.browser.calls == 1


@pytest.mark.parametrize("stage", ["executing", "sealed"])
def test_journal_commit_lost_ack_keeps_known_facts_and_never_reexecutes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    c = task_case(tmp_path / stage)
    original_append = c.deps.runs.append
    original = OSError("original " + stage + " acknowledgement lost")

    def append(
        entry: JournalEntry, revision: int, operation: OperationContext
    ) -> RunSnapshot:
        result = original_append(entry, revision, operation)
        if entry.event.stage == stage:
            raise original
        return result

    monkeypatch.setattr(c.deps.runs, "append", append)
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    error = caught.value
    assert error.primary is original or original in error.cleanup_errors
    assert "reset" in error.known
    assert c.model.calls == c.browser.calls == (1 if stage == "sealed" else 0)
    before = list(c.phases.calls)
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(c.plan, c.deps)
    assert c.phases.calls == before
    assert c.deps.runs.read(command()).project()[1][0].stage == "sealed"


@pytest.mark.parametrize("bad", [None, True, "", [], {}, 7])
def test_illegal_task_plan_fails_before_any_dependency(bad: object) -> None:
    with pytest.raises(ValidationError):
        execute_task(cast(TaskExecutionPlan, bad), cast(TaskExecutionDeps, object()))


def test_task_plan_rejects_version_scope_role_and_extreme_values_before_journal_changes(
    tmp_path: Path,
) -> None:
    c = task_case(tmp_path / "contract")
    before = c.deps.runs.read(command())
    cases = [
        ("schema_version", "task-execution-plan/2"),
        ("cleanup_seconds", 0),
        ("cleanup_seconds", 3601),
        ("cleanup_seconds", 2**256),
        ("cleanup_seconds", True),
        ("extra", True),
    ]
    for name, value in cases:
        raw = c.plan.model_dump(mode="python")
        raw[name] = value
        with pytest.raises(ValidationError):
            execute_task(cast(TaskExecutionPlan, raw), c.deps)
    for name, value in [
        ("owner_id", "foreign-owner"),
        ("attempt_id", None),
        ("mode", "cleanup"),
        ("operation_id", "x" * 201),
    ]:
        raw = c.plan.model_dump(mode="python")
        raw["operation"][name] = value
        if name == "mode":
            raw["operation"]["parent_operation_id"] = "original"
        with pytest.raises(ValidationError):
            execute_task(cast(TaskExecutionPlan, raw), c.deps)
    for name, value in [
        ("attempt_id", "foreign-attempt"),
        ("public_task_ref", c.plan.reset_plan_ref),
    ]:
        raw = c.plan.model_dump(mode="python")
        raw["evaluation"][name] = value
        with pytest.raises(ValidationError):
            execute_task(cast(TaskExecutionPlan, raw), c.deps)
    assert c.deps.runs.read(command()) == before and not c.phases.calls
