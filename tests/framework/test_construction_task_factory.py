"""Pure factory/current entry once, exact original handles, failures and isolation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.ledger.construction_journal import (
    FileConstructionJournal,
)
from lab_generate_skill.bootstrap.construction_task_execution import (
    RecordedConstructionTasks,
    ConstructionTaskFactoryUnconfirmed,
)
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.ports.construction import ConstructionSourceProof
from construction_task_factory_fixtures import original_factory_case


def test_factory_invokes_same_original_task_once_and_keeps_saved_result(
    tmp_path: Path,
) -> None:
    c, d, task = original_factory_case(tmp_path / "case")
    assert isinstance(d.journal, FileConstructionJournal)
    called = []

    def factory(intent: Any, op: Any, control: Any) -> RecordedConstructionTask:
        control.checkpoint()
        assert intent == task.plan.intent and op == task.plan.operation
        assert c.phases.calls == [] and c.model.calls == 0
        called.append(intent)
        return task

    port = RecordedConstructionTasks(d, c.plan.read_operation, d.journal, factory)
    result = port.execute(c.plan.intent, c.plan.operation)
    assert result.intent == c.plan.intent and result.evaluation.status == "failure"
    assert (
        called == [c.plan.intent]
        and port.tasks[c.plan.intent.binding.attempt_id] is task
    )
    before = c.model.calls
    with pytest.raises(DispatchAlreadyCommitted):
        port.execute(c.plan.intent, c.plan.operation)
    assert c.model.calls == before == 1
    # A fresh adapter object still cannot use the original registered attempt.
    again = RecordedConstructionTasks(d, c.plan.read_operation, d.journal, factory)
    with pytest.raises(ConstructionTaskFactoryUnconfirmed) as caught:
        again.execute(c.plan.intent, c.plan.operation)
    assert isinstance(caught.value.primary, DispatchAlreadyCommitted)
    assert len(called) == 1 and c.model.calls == before


@pytest.mark.parametrize("bad", [None, "", [], {}, True, 0])
def test_wrong_factory_packet_keeps_original_unknown_and_never_dispatches(
    tmp_path: Path, bad: Any
) -> None:
    c, d, task = original_factory_case(tmp_path / "case")
    assert isinstance(d.journal, FileConstructionJournal)
    calls = []

    def invalid(*args: Any) -> RecordedConstructionTask:
        calls.append(True)
        return cast(RecordedConstructionTask, bad)

    port = RecordedConstructionTasks(d, c.plan.read_operation, d.journal, invalid)
    with pytest.raises(ConstructionTaskFactoryUnconfirmed) as caught:
        port.execute(c.plan.intent, c.plan.operation)
    assert caught.value.phase == "pure_factory" and isinstance(
        caught.value.primary, TypeError
    )
    assert c.phases.calls == [] and c.model.calls == 0
    with pytest.raises(DispatchAlreadyCommitted):
        port.execute(c.plan.intent, c.plan.operation)
    assert calls == [True]


@pytest.mark.parametrize(
    "field",
    ["operation", "intent", "journal", "runs", "controls", "evidence", "claims"],
)
def test_substituted_original_binding_or_handle_refused_before_acquire(
    tmp_path: Path, field: str
) -> None:
    c, d, task = original_factory_case(tmp_path / "case")
    assert isinstance(d.journal, FileConstructionJournal)
    changed = task
    if field == "operation":
        changed = RecordedConstructionTask(
            c.plan.model_copy(
                update={
                    "operation": c.plan.operation.model_copy(
                        update={"operation_id": "other-invoke"}
                    )
                }
            ),
            c.deps,
        )
    elif field == "intent":
        changed = RecordedConstructionTask(
            c.plan.model_copy(
                update={
                    "intent": c.plan.intent.model_copy(
                        update={"skill_digest": "f" * 64}
                    )
                }
            ),
            c.deps,
        )
    else:
        key = "construction" if field == "journal" else field
        altered = (
            replace(c.deps.admission, claims=cast(Any, object()))
            if field == "claims"
            else c.deps.admission
        )
        changes: dict[str, Any] = (
            {"admission": altered} if field == "claims" else {key: object()}
        )
        changed = RecordedConstructionTask(c.plan, replace(c.deps, **changes))
    port = RecordedConstructionTasks(
        d, c.plan.read_operation, d.journal, lambda *args: changed
    )
    with pytest.raises(ConstructionTaskFactoryUnconfirmed) as caught:
        port.execute(c.plan.intent, c.plan.operation)
    assert caught.value.phase == "pure_factory" and isinstance(
        caught.value.primary, OwnershipConflict
    )
    assert c.phases.calls == [] and c.model.calls == 0 and caught.value.task is changed


@pytest.mark.parametrize("cancel", [False, True])
def test_factory_partial_or_cancel_error_retained_without_replacement(
    tmp_path: Path, cancel: bool
) -> None:
    c, d, task = original_factory_case(tmp_path / "case")
    assert isinstance(d.journal, FileConstructionJournal)
    original = (
        OperationStopped("CANCELLED", c.plan.operation.operation_id)
        if cancel
        else TimeoutError("original pure factory response lost")
    )
    calls = []

    def failed(*args: Any) -> RecordedConstructionTask:
        calls.append(True)
        raise original

    port = RecordedConstructionTasks(d, c.plan.read_operation, d.journal, failed)
    with pytest.raises(ConstructionTaskFactoryUnconfirmed) as caught:
        port.execute(c.plan.intent, c.plan.operation)
    assert caught.value.primary is original and caught.value.task is None
    assert c.phases.calls == [] and c.model.calls == 0
    with pytest.raises(DispatchAlreadyCommitted):
        port.execute(c.plan.intent, c.plan.operation)
    assert calls == [True]


def test_missing_original_source_and_cross_thread_cannot_build_task(
    tmp_path: Path,
) -> None:
    c, d, task = original_factory_case(tmp_path / "case")
    assert isinstance(d.journal, FileConstructionJournal)
    called = []

    def factory(*args: Any) -> RecordedConstructionTask:
        called.append(True)
        return task

    with pytest.raises(ValueError):
        RecordedConstructionTasks(
            d, c.plan.read_operation, cast(ConstructionSourceProof, None), factory
        )
    port = RecordedConstructionTasks(d, c.plan.read_operation, d.journal, factory)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(port.execute, c.plan.intent, c.plan.operation).result()
    assert called == [] and c.phases.calls == []


def test_another_attempt_id_cannot_bypass_original_pending_intent(
    tmp_path: Path,
) -> None:
    c, d, task = original_factory_case(tmp_path / "case")
    assert isinstance(d.journal, FileConstructionJournal)
    called = []

    def factory(*args: Any) -> RecordedConstructionTask:
        called.append(True)
        return task

    port = RecordedConstructionTasks(d, c.plan.read_operation, d.journal, factory)
    other = c.plan.intent.model_copy(
        update={
            "binding": c.plan.intent.binding.model_copy(
                update={"attempt_id": "other-attempt"}
            )
        }
    )
    op = c.plan.operation.model_copy(
        update={"attempt_id": "other-attempt", "operation_id": "other-attempt-invoke"}
    )
    with pytest.raises(ConstructionTaskFactoryUnconfirmed) as caught:
        port.execute(other, op)
    assert isinstance(caught.value.primary, OwnershipConflict)
    assert caught.value.phase == "original_source" and called == []
    assert c.phases.calls == [] and c.model.calls == 0


def test_revoked_original_source_stops_before_any_factory_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, d, task = original_factory_case(tmp_path / "case")
    assert isinstance(d.journal, FileConstructionJournal)
    called = []

    def factory(*args: Any) -> RecordedConstructionTask:
        called.append(True)
        return task

    original = PermissionError("original construction source revoked")

    def refused(*args: Any, **kwargs: Any) -> None:
        raise original

    monkeypatch.setattr(c.admission.data.authority, "verify_plan", refused)
    port = RecordedConstructionTasks(d, c.plan.read_operation, d.journal, factory)
    with pytest.raises(ConstructionTaskFactoryUnconfirmed) as caught:
        port.execute(c.plan.intent, c.plan.operation)
    assert caught.value.primary is original and called == [] and c.phases.calls == []
