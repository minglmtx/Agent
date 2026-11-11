"""Finite construction Teacher glue boundaries over original ports only."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.construct_targets import (
    construct_targets,
    ConstructionStepUnconfirmed,
)
from lab_generate_skill.bootstrap.construction_teacher import (
    completed_task_teacher_dependencies,
)
from lab_generate_skill.domain.construction import CallCompleted, ProgressEvent
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction_control import RecordConstructionWork
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from task_teacher_control_fixtures import (
    task_teacher_control_case,
    TaskTeacherControlCase,
)
from test_run_journal import command


def bind(c: TaskTeacherControlCase, **changes: Any) -> Any:
    args: dict[str, Any] = dict(
        ledger=c.wire.ledger,
        transport=c.wire.transport,
        send_authority=c.wire.send_authority,
        counts=c.wire.count_review,
        read_operation=c.wire.original.settlement_operation,
        journal_with_review=lambda proof: c.source.data.journal(teacher_review=proof),
    )
    args.update(changes)
    return completed_task_teacher_dependencies(
        c.deps, c.wire.deps, c.wire.review, **args
    )


@pytest.fixture(scope="module")
def ready(tmp_path_factory: pytest.TempPathFactory) -> Any:
    with pytest.MonkeyPatch.context() as patch:
        c = task_teacher_control_case(
            tmp_path_factory.mktemp("task-control") / "case", patch
        )
        c.source.native.client.close(c.deps.controls.bind(c.source.bindings.operation))
        yield c


@pytest.mark.parametrize(
    "name",
    [
        "ledger",
        "transport",
        "send_authority",
        "counts",
        "read_operation",
        "journal_with_review",
    ],
)
@pytest.mark.parametrize("bad", [None, {}, [], "", True, 0])
def test_required_native_ports_reject_missing_empty_wrong_type_before_effects(
    ready: TaskTeacherControlCase, name: str, bad: Any
) -> None:
    calls = ready.source.native.loader.session.calls
    before = ready.deps.journal.read(command())
    with pytest.raises(ValueError):
        bind(ready, **{name: bad})
    assert ready.deps.journal.read(command()) == before
    assert (
        not ready.wire.transport.calls
        and ready.source.native.loader.session.calls == calls
    )


@pytest.mark.parametrize(
    "kind",
    [
        "readiness",
        "assembly-journal",
        "review-journal",
        "CAS",
        "source-null",
        "context-null",
        "context-role",
        "source-role",
    ],
)
def test_original_source_context_journal_role_and_CAS_cannot_be_mixed(
    ready: TaskTeacherControlCase, kind: str
) -> None:
    c = ready
    construction, assembly, review = c.deps, c.wire.deps, c.wire.review
    invalid: Any = object()
    absent: Any = None
    if kind == "readiness":
        construction = replace(construction, readiness=None)
    elif kind == "assembly-journal":
        assembly = replace(assembly, journal=invalid)
    elif kind == "review-journal":
        review = replace(review, journal=invalid)
    elif kind == "CAS":
        review = replace(review, evidence=invalid)
    elif kind == "source-null":
        review = replace(review, source=absent)
    elif kind == "context-null":
        review = replace(review, context=absent)
    elif kind == "context-role":
        review = replace(review, context=replace(review.context, authority=invalid))
    else:
        review = replace(review, source=replace(review.source, authority=invalid))
    with pytest.raises(ValueError):
        completed_task_teacher_dependencies(
            construction,
            assembly,
            review,
            ledger=c.wire.ledger,
            transport=c.wire.transport,
            send_authority=c.wire.send_authority,
            counts=c.wire.count_review,
            read_operation=c.wire.original.settlement_operation,
            journal_with_review=lambda proof: c.source.data.journal(
                teacher_review=proof
            ),
        )
    assert not c.wire.transport.calls


def test_rebinding_is_pure_and_keeps_original_non_Teacher_dependencies(
    ready: TaskTeacherControlCase,
) -> None:
    c = ready
    before = c.deps.journal.read(command())
    a, b = bind(c), bind(c)
    assert a.journal is b.journal is c.deps.journal
    assert a.readiness is b.readiness is c.deps.readiness
    assert a.teacher_assembly is b.teacher_assembly is c.wire.deps
    assert a.attempts is b.attempts is c.deps.attempts
    assert a.generator is b.generator is c.deps.generator
    assert c.deps.journal.read(command()) == before and not c.wire.transport.calls


def test_unknown_Teacher_response_remains_pending_without_automatic_reinvoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = task_teacher_control_case(tmp_path / "case", monkeypatch)
    c.wire.transport.error = OSError("original Teacher send response unconfirmed")
    step = c.step()
    with pytest.raises(ConstructionStepUnconfirmed) as caught:
        construct_targets(step, c.deps)
    assert caught.value.phase == "original_teacher" and caught.value.response is None
    original = c.deps.journal.read(command())
    assert original.project().pending_call is not None
    assert construct_targets(step, c.deps).status == "waiting"
    assert c.deps.journal.read(command()) == original
    assert (
        len(c.wire.transport.calls) == 1 and c.source.native.loader.session.calls == 4
    )
    c.source.native.client.close(c.deps.controls.bind(c.source.bindings.operation))


class FailedCompletionJournal:
    def __init__(self, original: ConstructionJournal, error: BaseException) -> None:
        self.original, self.error = original, error

    def read(self, op: OperationContext) -> ConstructionProgress:
        return self.original.read(op)

    def create(self, plan: Any, op: OperationContext) -> ConstructionProgress:
        raise AssertionError("No new construction journal may be created")

    def append(
        self, event: ProgressEvent, expected_revision: int, op: OperationContext
    ) -> ConstructionProgress:
        raise self.error


def test_known_Teacher_return_with_failed_commit_reconciles_same_fact_without_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = task_teacher_control_case(tmp_path / "case", monkeypatch)
    error = OSError("original Teacher completion journal unavailable")

    def broken(proof: TeacherConstructionVerifier) -> ConstructionJournal:
        return FailedCompletionJournal(
            c.source.data.journal(teacher_review=proof), error
        )

    failing = bind(c, journal_with_review=broken)
    with pytest.raises(ConstructionStepUnconfirmed) as caught:
        construct_targets(c.step(), failing)
    known = caught.value
    assert known.phase == "complete_original_teacher" and known.primary is error
    assert (
        isinstance(known.event, CallCompleted)
        and known.response is not None
        and known.teacher is not None
    )
    assert len(c.wire.transport.calls) == 1
    step = c.step().model_copy(
        update={
            "expected_revision": known.progress.revision,
            "operation": known.event.operation,
            "work": RecordConstructionWork(event=known.event, teacher=known.teacher),
        }
    )
    actual = construct_targets(step, c.deps)
    assert (
        actual.status == "advanced" and actual.progress.project().pending_call is None
    )
    assert (
        len(c.wire.transport.calls) == 1 and c.source.native.loader.session.calls == 4
    )
    c.source.native.client.close(c.deps.controls.bind(c.source.bindings.operation))
