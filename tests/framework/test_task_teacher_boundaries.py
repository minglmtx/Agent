"""Bridge boundary checks reuse cheap original completed lifecycle fixtures."""

from dataclasses import replace
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.task_teacher_inputs import task_teacher_input
from lab_generate_skill.application.task_teacher import (
    publish_task_teacher_attempt,
    TaskTeacherUnconfirmed,
)
from lab_generate_skill.domain.task_teacher import TaskTeacherInput
from lab_generate_skill.domain.task_execution_result import (
    ExecutedTaskReceipt,
    TaskAttemptResult,
)
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from construction_storage_fixtures import put
from task_teacher_fixtures import completed_case, native_deps
from teacher_attempt_fixtures import UnitNativeAuthority


@pytest.mark.parametrize(
    "fault", ["counters", "context", "old_envelope", "trace", "capture", "closure"]
)
def test_task_teacher_rejects_changed_lineage_before_native_publication(
    tmp_path: Path, fault: str
) -> None:
    c = completed_case(tmp_path / fault)
    original, store = c.original, c.task.admission.data.store
    if fault == "counters":
        original = original.model_copy(
            update={
                "result": original.result.model_copy(
                    update={"generations": original.result.generations + 1}
                )
            }
        )
    elif fault == "context":
        original = original.model_copy(
            update={
                "scope": original.scope.model_copy(
                    update={"context_id": "another-context"}
                )
            }
        )
    elif fault == "old_envelope":
        ref = store.put(
            b'{"unit_closed":true}',
            EvidenceMetadata(
                media_type="application/json",
                content_schema="attempt-result/1",
                visibility="private",
                producer="unit-old-result",
            ),
        )
        original = original.model_copy(
            update={"result": original.result.model_copy(update={"attempt_ref": ref})}
        )
    elif fault == "closure":
        c.task.phases.closure_denied = True
    else:
        envelope = TaskAttemptResult.model_validate_json(
            store.read(original.result.attempt_ref)
        )
        executed = ExecutedTaskReceipt.model_validate_json(
            store.read(envelope.execution_ref)
        )
        field = "trace_ref" if fault == "trace" else "capture_ref"
        ref = getattr(executed, field)
        foreign = ref.model_copy(update={"producer": "another-original-producer"})
        executed = executed.model_copy(update={field: foreign})
        env = envelope.model_copy(
            update={"execution_ref": put(store, executed, "executed-task-receipt/1")}
        )
        original = original.model_copy(
            update={
                "result": original.result.model_copy(
                    update={"attempt_ref": put(store, env, "attempt-result/1")}
                )
            }
        )
    authority = UnitNativeAuthority()
    deps = native_deps(c.task, authority)
    with pytest.raises(TaskTeacherUnconfirmed) as caught:
        publish_task_teacher_attempt(
            original, deps, control=c.task.deps.controls.bind(original.operation)
        )
    assert (
        caught.value.phase == "original_task"
        and caught.value.part is None
        and not caught.value.retained
    )
    assert isinstance(
        caught.value.primary,
        (ValueError, EvidenceIntegrityError, OwnershipConflict, PermissionError),
    )
    assert authority.calls == 0 and c.task.model.calls == c.task.browser.calls == 1


@pytest.mark.parametrize("fault", ["unsealed", "changed_during_read"])
def test_task_teacher_requires_stable_original_sealed_history(
    tmp_path: Path, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = completed_case(tmp_path / fault)
    read = c.task.deps.runs.read
    snapshot = read(c.original.operation)
    previous = snapshot.model_copy(update={"entries": snapshot.entries[:-1]})
    calls = 0

    def observed(op: OperationContext) -> RunSnapshot:
        nonlocal calls
        calls += 1
        return previous if fault == "unsealed" or calls == 2 else snapshot

    monkeypatch.setattr(c.task.deps.runs, "read", observed)
    with pytest.raises(OwnershipConflict):
        task_teacher_input(
            c.original,
            c.reads,
            c.original.operation,
            control=c.task.deps.controls.bind(c.original.operation),
        )
    assert c.task.model.calls == c.task.browser.calls == 1


@pytest.mark.parametrize("error", [TimeoutError, InterruptedError])
def test_bridge_timeout_cancel_before_read_never_publishes_or_reexecutes(
    tmp_path: Path, error: type[Exception]
) -> None:
    c = completed_case(tmp_path / "case")

    class Stopped:
        def checkpoint(self) -> None:
            raise error("unit stopped original material read")

    authority = UnitNativeAuthority()
    with pytest.raises(TaskTeacherUnconfirmed) as caught:
        publish_task_teacher_attempt(
            c.original,
            native_deps(c.task, authority),
            control=cast(OperationControl, Stopped()),
        )
    assert (
        isinstance(caught.value.primary, error)
        and not caught.value.retained
        and caught.value.part is None
    )
    assert authority.calls == 0 and c.task.model.calls == c.task.browser.calls == 1


@pytest.mark.parametrize("value", [None, "", [], 7, {}, {"result": None}])
def test_invalid_task_teacher_contract_never_touches_dependencies(
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        TaskTeacherInput.model_validate(value)


def test_task_teacher_valid_input_still_requires_original_feedback_and_no_writes(
    tmp_path: Path,
) -> None:
    c = completed_case(tmp_path / "case")
    source = task_teacher_input(
        c.original,
        c.reads,
        c.original.operation,
        control=c.task.deps.controls.bind(c.original.operation),
    )
    assert source.candidate_slot == c.original.result.intent.candidate_slot
    assert (
        source.evaluation_ref == c.original.result.evaluation_ref
        and source.feedback == c.original.feedback
    )
    with pytest.raises(ValueError, match="authorities required"):
        replace(c.reads, closure=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        TaskTeacherInput.model_validate(
            {**c.original.model_dump(), "operation": c.task.plan.operation.model_dump()}
        )


@pytest.mark.parametrize("fact", ["baseline", "reset"])
def test_task_teacher_rejects_changed_state_reader_before_native_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fact: str
) -> None:
    c = completed_case(tmp_path / fact)
    states = c.task.deps.states
    name = "load_" + fact
    original = getattr(states, name)

    def changed(*args: object, **kwargs: object) -> object:
        value = original(*args, **kwargs)
        return value.model_copy(
            update={"status": "unknown" if fact == "baseline" else "quarantined"}
        )

    monkeypatch.setattr(states, name, changed)
    authority = UnitNativeAuthority()
    with pytest.raises(TaskTeacherUnconfirmed) as caught:
        publish_task_teacher_attempt(
            c.original,
            native_deps(c.task, authority),
            control=c.task.deps.controls.bind(c.original.operation),
        )
    assert isinstance(caught.value.primary, EvidenceIntegrityError)
    assert (
        caught.value.part is None and not caught.value.retained and authority.calls == 0
    )


def test_task_teacher_role_and_feedback_limits_are_strict(tmp_path: Path) -> None:
    c = completed_case(tmp_path / "case")
    raw = c.original.model_dump()
    raw["scope"]["role"] = "actor"
    with pytest.raises(ValidationError):
        TaskTeacherInput.model_validate(raw)
    raw = c.original.model_dump()
    raw["feedback"]["authorization_ref"]["size_bytes"] = 1024**2 + 1
    with pytest.raises(ValidationError):
        TaskTeacherInput.model_validate(raw)
