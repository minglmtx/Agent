"""Original task journal diagnostic survives module errors without claiming candidates."""

from pathlib import Path
import pytest
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.application.task_execution_events import task_stop_reason
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.task_execution_result import TaskFailureContext
from lab_generate_skill.domain.task_failure_evidence import TaskModuleFailureEvidence
from task_execution_fixtures import task_case
from retrieval_fixtures import reference


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("CANCELLED", "cancelled"),
        ("DEADLINE_EXCEEDED", "timeout"),
        ("known-error", "error"),
    ],
)
def test_module_partial_refs_and_wrapped_stop_survive_actual_task_diagnostic(
    tmp_path: Path, reason: str, expected: str
) -> None:
    c = task_case(tmp_path / "task")
    store = c.admission.data.store
    confirmed = reference(
        {"actual_saved_full_bytes": True}, "browser-capture-intent/1", store=store
    )
    candidate = reference({"candidate_not_saved": True}, "browser-capture-result/1")

    class ModuleError(RuntimeError):
        primary: BaseException
        references = (confirmed,)
        candidates = (candidate,)

    failure = ModuleError("Explicit test module failure")
    failure.primary = (
        OperationStopped(reason, c.plan.operation.operation_id)
        if reason != "known-error"
        else ValueError("unit root")
    )
    c.phases.errors["capture"] = failure
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    assert caught.value.primary is failure
    context = TaskFailureContext.model_validate_json(
        store.read(caught.value.known["primary_failure_context"])
    )
    module_ref = next(
        ref
        for ref in context.references
        if ref.content_schema == "task-module-failure-evidence/1"
    )
    module = TaskModuleFailureEvidence.model_validate_json(store.read(module_ref))
    assert module.intent == c.plan.intent and module.confirmed_references == (
        confirmed,
    )
    assert (
        module.candidate_references == (candidate,)
        and module.malformed_attributes == ()
    )
    assert confirmed in context.references and candidate not in context.references
    events = c.deps.runs.read(c.plan.read_operation).project()[1][0].events
    assert (
        next(event for event in events if event.stage == "closing").stop_reason
        == expected
    )
    assert "reset" in caught.value.known and c.model.calls == c.browser.calls == 1


def test_malformed_module_attributes_are_recorded_without_leaking_values(
    tmp_path: Path,
) -> None:
    c = task_case(tmp_path / "task")
    failure = RuntimeError("never serialize this arbitrary backend message")
    setattr(failure, "references", ["backend secret"])
    setattr(failure, "candidates", None)
    c.phases.errors["capture"] = failure
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    store = c.admission.data.store
    context = TaskFailureContext.model_validate_json(
        store.read(caught.value.known["primary_failure_context"])
    )
    ref = next(
        r
        for r in context.references
        if r.content_schema == "task-module-failure-evidence/1"
    )
    raw = store.read(ref)
    value = TaskModuleFailureEvidence.model_validate_json(raw)
    assert value.confirmed_references == value.candidate_references == ()
    assert value.malformed_attributes == ("references:list", "candidates:NoneType")
    assert b"backend secret" not in raw and b"backend message" not in raw


def test_stop_chain_cycles_and_non_exception_primary_cannot_invent_cancellation() -> (
    None
):
    value = RuntimeError("unit cyclic wrapper")
    setattr(value, "primary", value)
    assert task_stop_reason(value) == "error"
    setattr(value, "primary", "CANCELLED")
    assert task_stop_reason(value) == "error"
    assert task_stop_reason(None) is None
