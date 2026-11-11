"""Original method boundaries: no pending replay; known facts survive lost ACKs.

All role/closure facts are explicit unit fixtures, never business acceptance.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.construct_targets import (
    ConstructionStepUnconfirmed,
    construct_targets,
    ConstructionDeps,
)
from lab_generate_skill.application.teacher_assembly import assemble_teacher_revision
from lab_generate_skill.domain.construction import CallCompleted, CallUncertain
from lab_generate_skill.domain.construction_control import (
    ConstructionStepPlan,
    GenerateConstructionWork,
    RecordConstructionWork,
    ReviseConstructionWork,
)
from lab_generate_skill.domain.construction_inputs import RevisionInput, RevisionResult
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.teacher_assembly import PublishedTeacherRevisionAssembly
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.teacher import Teacher
from construction_control_fixtures import control_case
from construction_control_generation_fixtures import (
    generation_case,
    CompletionAcknowledgmentFault,
)
from construction_storage_fixtures import put
from test_teacher_source_admission_boundaries import error_stop
from test_run_journal import command


def test_generator_uses_registered_complete_public_input_once(tmp_path: Path) -> None:
    c = generation_case(tmp_path / "generator")
    step = c.step()
    result = construct_targets(step, c.deps)
    assert (
        result.status == "advanced"
        and result.progress.project().next_action.kind == "generate"
    )
    assert result.progress.project().next_action.candidate_slot == 1
    assert isinstance(step.work, GenerateConstructionWork)
    assert c.generator.calls == [step.work.request]
    assert len(c.generator.calls[0].retrieved_skills) == 6
    assert (
        c.data.store.read(step.work.planned.call.input_ref)
        == step.work.request.model_dump_json().encode()
    )
    with pytest.raises(RevisionConflict):
        construct_targets(step, c.deps)
    assert len(c.generator.calls) == 1


@pytest.mark.parametrize("failure", ["timeout", "cancel", "partial"])
def test_generator_failure_retains_pending_and_unknown_without_reinvoke(
    tmp_path: Path, failure: str
) -> None:
    c = generation_case(tmp_path / failure)
    step = c.step()
    original = (
        OperationStopped("CANCELLED", "original-generator")
        if failure == "cancel"
        else (
            TimeoutError("original generator timeout")
            if failure == "timeout"
            else OSError("original provider partial failure")
        )
    )
    c.generator.error = original
    with pytest.raises(ConstructionStepUnconfirmed) as captured:
        construct_targets(step, c.deps)
    error = captured.value
    assert error.primary is original and error.__cause__ is original
    assert error.phase == "original_generator" and error.response is None
    current = c.deps.journal.read(command())
    pending = current.project().pending_call
    assert (
        pending is not None and current.project().next_action.kind == "await_response"
    )
    assert construct_targets(step, c.deps).status == "waiting"
    note = CallUncertain(
        operation=command("control-original-unknown"),
        request_id=pending.request_id,
        evidence_ref=put(c.data.store, {"unknown_request": pending.request_id}),
    )
    recorded = construct_targets(
        ConstructionStepPlan(
            run=step.run,
            expected_revision=current.revision,
            operation=note.operation,
            work=RecordConstructionWork(event=note),
        ),
        replace(c.deps, readiness=None, generator=None, evidence=None),
    )
    assert recorded.progress.project().next_action.kind in ("await_response", "blocked")
    assert construct_targets(step, c.deps).status == "waiting"
    assert len(c.generator.calls) == 1


@pytest.mark.parametrize("commit_first", [False, True])
def test_returned_teacher_result_records_after_stop_without_reinvoke(
    tmp_path: Path, commit_first: bool
) -> None:
    c = control_case(tmp_path / "teacher")
    binder = c.deps.teacher_journal
    assert binder is not None
    original = OSError("original completion acknowledgement unavailable")

    def faulty(published: PublishedTeacherRevisionAssembly) -> ConstructionJournal:
        return CompletionAcknowledgmentFault(
            binder(published), original, commit_first=commit_first
        )

    step = c.teacher_step()
    with pytest.raises(ConstructionStepUnconfirmed) as captured:
        construct_targets(step, replace(c.deps, teacher_journal=faulty))
    error = captured.value
    assert error.phase == "complete_original_teacher" and error.primary is original
    assert isinstance(error.response, RevisionResult) and isinstance(
        error.event, CallCompleted
    )
    assert error.event.response == error.response and error.teacher is not None
    assert len(c.native.transport.calls) == 1
    actual = c.deps.journal.read(command())
    assert (actual.project().pending_call is None) == commit_first
    snapshot = c.source.runs.read(command())
    stop = error_stop(snapshot, c.source)
    c.source.runs.append(stop, snapshot.revision, stop.event.operation)
    # This command has only the original append proof; no execution gate or role.
    cleanup = error.event.operation.cleanup(
        "control-record-returned-teacher", now=datetime.now(timezone.utc), seconds=60
    )
    record = ConstructionStepPlan(
        run=step.run,
        expected_revision=error.progress.revision,
        operation=cleanup,
        work=RecordConstructionWork(event=error.event, teacher=error.teacher),
    )
    record_deps = replace(
        c.deps,
        readiness=None,
        teacher_assembly=None,
        teacher_factory=None,
        attempts=None,
        teacher_journal=binder,
    )
    result = construct_targets(record, record_deps)
    assert result.progress.project().next_action.kind == "execute"
    assert result.progress.events[-1] == error.event
    repeated = construct_targets(record, record_deps)
    assert repeated.progress == result.progress
    assert len(c.native.transport.calls) == 1 and len(c.publications) == 1


@pytest.mark.parametrize("unknown", [False, True])
def test_existing_teacher_pending_or_unknown_is_observed_without_binding_roles(
    tmp_path: Path, unknown: bool
) -> None:
    c = control_case(tmp_path / "teacher-pending")
    step = c.teacher_step()
    assert isinstance(step.work, ReviseConstructionWork)
    pub = assemble_teacher_revision(
        step.work.original,
        c.native.deps,
        control=c.native.source.controls.bind(step.operation),
    )
    current = c.deps.journal.read(command())
    if unknown:
        note = CallUncertain(
            operation=command("controlled-unknown-teacher"),
            request_id=pub.bound.plan.revision.request_id,
            evidence_ref=put(
                c.native.source.data.store,
                {"unknown_request": pub.bound.plan.revision.request_id},
            ),
        )
        current = c.deps.journal.append(note, current.revision, note.operation)
    minimal = replace(
        c.deps,
        readiness=None,
        teacher_factory=None,
        teacher_assembly=None,
        teacher_journal=None,
    )
    result = construct_targets(step, minimal)
    assert result.status == "waiting" and result.progress == current
    assert not c.publications and not c.native.transport.calls


@pytest.mark.parametrize(
    "fault", ["missing_role", "stopped", "claim", "writer", "stale"]
)
def test_teacher_new_work_admission_rejects_before_registration_or_send(
    tmp_path: Path, fault: str
) -> None:
    c = control_case(tmp_path / fault)
    step = c.teacher_step()
    before = c.deps.journal.read(command())
    deps = c.deps
    expected: type[Exception]
    if fault == "missing_role":
        deps = replace(deps, teacher_factory=None)
        expected = ValueError
    elif fault == "stopped":
        snapshot = c.source.runs.read(command())
        event = error_stop(snapshot, c.source)
        c.source.runs.append(event, snapshot.revision, event.event.operation)
        expected = InvalidTransition
    elif fault == "claim":
        c.native.source.data.claim_authority.denied = True
        expected = OwnershipConflict
    elif fault == "writer":
        c.native.source.data.authority.denied = True
        expected = OwnershipConflict
    else:
        step = ConstructionStepPlan.model_validate(
            step.model_copy(update={"expected_revision": before.revision - 1})
        )
        expected = RevisionConflict
    with pytest.raises(expected):
        construct_targets(step, deps)
    assert c.deps.journal.read(command()) == before
    assert not c.publications and not c.native.transport.calls


@pytest.mark.parametrize(
    "fault", ["readiness", "generator", "bytes", "completion_expired"]
)
def test_generator_rejects_missing_admission_or_changed_bytes_before_dispatch(
    tmp_path: Path, fault: str
) -> None:
    c = generation_case(tmp_path / fault)
    step = c.step()
    assert isinstance(step.work, GenerateConstructionWork)
    work = step.work
    deps = c.deps
    expected: type[Exception] = ValueError
    if fault == "readiness":
        deps = replace(deps, readiness=None)
    elif fault == "generator":
        deps = replace(deps, generator=None)
    elif fault == "bytes":
        request = work.request.model_copy(
            update={
                "context": work.request.context.model_copy(
                    update={"context_id": "changed-original-context"}
                )
            }
        )
        step = ConstructionStepPlan.model_validate(
            step.model_copy(
                update={"work": work.model_copy(update={"request": request})}
            )
        )
        expected = ConstructionStepUnconfirmed
    else:
        expired = work.completion_operation.model_copy(
            update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        step = ConstructionStepPlan.model_validate(
            step.model_copy(
                update={
                    "work": work.model_copy(update={"completion_operation": expired})
                }
            )
        )
        expected = OperationStopped
    before = c.deps.journal.read(command())
    with pytest.raises(expected) as captured:
        construct_targets(step, deps)
    if fault == "bytes":
        assert isinstance(captured.value, ConstructionStepUnconfirmed)
        assert isinstance(captured.value.primary, OwnershipConflict)
    assert c.deps.journal.read(command()) == before and not c.generator.calls


@pytest.mark.parametrize("bad", [None, True, "", [], {}, 7])
def test_invalid_control_payload_rejects_before_dependencies(bad: object) -> None:
    deps = ConstructionDeps(
        cast(ConstructionJournal, object()), cast(OperationControls, object())
    )
    with pytest.raises(ValidationError):
        construct_targets(cast(ConstructionStepPlan, bad), deps)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "extra",
        "negative_revision",
        "huge_revision",
        "bool_revision",
        "owner",
        "attempt",
        "cleanup_new_work",
        "duplicate_operation",
        "completion_parent",
        "role",
    ],
)
def test_step_contract_rejects_version_type_scope_role_and_operation_conflicts(
    tmp_path: Path, mutation: str
) -> None:
    c = generation_case(tmp_path / mutation)
    step = c.step()
    raw = step.model_dump(mode="python")
    if mutation == "version":
        raw["schema_version"] = "construction-step-plan/2"
    elif mutation == "extra":
        raw["silently_ignored"] = True
    elif mutation in ("negative_revision", "huge_revision", "bool_revision"):
        raw["expected_revision"] = {
            "negative_revision": -2,
            "huge_revision": 2**128,
            "bool_revision": True,
        }[mutation]
    elif mutation == "owner":
        raw["operation"]["owner_id"] = "other-owner"
    elif mutation == "attempt":
        raw["operation"]["attempt_id"] = "other-attempt"
    elif mutation == "cleanup_new_work":
        raw["operation"]["mode"] = "cleanup"
        raw["operation"]["parent_operation_id"] = "older-operation"
    elif mutation == "duplicate_operation":
        raw["work"]["invoke_operation"] = raw["operation"]
    elif mutation == "completion_parent":
        raw["work"]["completion_operation"][
            "parent_operation_id"
        ] = "unrelated-operation"
    else:
        raw["work"]["planned"]["call"]["role"] = "teacher"
    before = c.deps.journal.read(command())
    with pytest.raises(ValidationError):
        construct_targets(cast(ConstructionStepPlan, raw), c.deps)
    assert c.deps.journal.read(command()) == before and not c.generator.calls


@pytest.mark.parametrize("failure", ["timeout", "cancel"])
def test_teacher_role_error_retains_registered_pending_without_calling_again(
    tmp_path: Path, failure: str
) -> None:
    c = control_case(tmp_path / failure)
    error = (
        TimeoutError("original teacher outcome unknown")
        if failure == "timeout"
        else OperationStopped("CANCELLED", "original-teacher")
    )
    calls: list[RevisionInput] = []

    class FailingTeacher:
        def revise(
            self, request: RevisionInput, op: OperationContext
        ) -> RevisionResult:
            calls.append(request)
            raise error

    def bind(_: PublishedTeacherRevisionAssembly) -> Teacher:
        return FailingTeacher()

    deps = replace(c.deps, teacher_factory=bind)
    step = c.teacher_step()
    with pytest.raises(ConstructionStepUnconfirmed) as captured:
        construct_targets(step, deps)
    assert captured.value.primary is error and captured.value.teacher is not None
    assert (
        captured.value.phase == "original_teacher" and captured.value.response is None
    )
    assert construct_targets(step, deps).status == "waiting"
    assert len(calls) == 1 and not c.native.transport.calls


@pytest.mark.parametrize("failure", ["timeout", "cancel"])
def test_actor_lifecycle_partial_failure_retains_intent_without_reexecution(
    tmp_path: Path, failure: str
) -> None:
    c = control_case(tmp_path / failure)
    construct_targets(c.teacher_step(), c.deps)
    step = c.actor_step()
    original = (
        TimeoutError("original Actor closure unresolved")
        if failure == "timeout"
        else OperationStopped("CANCELLED", "original-actor")
    )
    c.attempts.error = original
    with pytest.raises(ConstructionStepUnconfirmed) as captured:
        construct_targets(step, c.deps)
    error = captured.value
    assert error.primary is original and error.phase == "original_actor_lifecycle"
    assert error.response is None
    current = c.deps.journal.read(command())
    assert current.project().next_action.kind == "await_attempt"
    assert current.project().pending_attempt == c.attempts.calls[0]
    minimal = replace(c.deps, attempts=None, readiness=None, teacher_factory=None)
    repeated = construct_targets(step, minimal)
    assert repeated.status == "waiting" and repeated.progress == current
    assert len(c.attempts.calls) == 1 and len(c.native.transport.calls) == 1


def test_valid_failed_actor_fact_advances_original_revision_schedule(
    tmp_path: Path,
) -> None:
    c = control_case(tmp_path / "valid-failure")
    construct_targets(c.teacher_step(), c.deps)
    step = c.actor_step()
    before = c.deps.journal.read(command())
    with pytest.raises(ValueError, match="complete Actor task lifecycle"):
        construct_targets(step, replace(c.deps, attempts=None))
    assert c.deps.journal.read(command()) == before
    c.attempts.status = "failure"
    result = construct_targets(step, c.deps)
    view = result.progress.project()
    assert result.status == "advanced"
    assert view.attempts[-1].evaluation.status == "failure"
    assert view.next_action.kind == "revise" and view.next_action.candidate_slot == 5
    assert len(c.attempts.calls) == 1 and len(c.native.transport.calls) == 1
