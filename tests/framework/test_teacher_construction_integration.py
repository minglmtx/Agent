"""Actual file construction consumer; model/source/byte-token rights synthetic.

The same prepared/native reply proof is consumed before the original journal
publishes Teacher v2. No actual model/tokenizer, source task, API or fee call.
"""

import os
from pathlib import Path
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
)
from lab_generate_skill.adapters.models.teacher_response import OpenRouterTeacherDecoder
from lab_generate_skill.bootstrap.teacher_revision import recorded_teacher_review
from lab_generate_skill.domain.construction import (
    CallPlanned,
    CallCompleted,
    ProgressEvent,
    ConstructionPlan,
)
from lab_generate_skill.domain.construction_inputs import RevisionResult
from lab_generate_skill.domain.construction_journal import ConstructionCommitUnconfirmed
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext, CancellationRef
from lab_generate_skill.domain.teacher_revision import TeacherRevisionExecution
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from lab_generate_skill.application.teacher_revision_review import (
    RecordedTeacherRevisionReview,
)
from construction_storage_fixtures import (
    fixture,
    StorageFixture,
    UnitConstructionAuthority,
)
from teacher_revision_fixtures import (
    revision_case,
    TeacherRevisionCase,
    WholeWireReview,
)
from source_review_records import ReadOnlyEvidence
from test_run_journal import command, CancelSwitch


class NativeTeacherUnitSourceAuthority(UnitConstructionAuthority):
    """Explicit fixture source authority; never installed in a production factory."""

    def verify_event(
        self, progress: ConstructionProgress, event: ProgressEvent, op: OperationContext
    ) -> None:
        native = (
            isinstance(event, CallPlanned)
            and event.call.request_id == "teacher-3-original"
        ) or (
            isinstance(event, CallCompleted)
            and isinstance(event.response, RevisionResult)
            and event.response.schema_version == "revision-result/2"
        )
        if not native:
            return super().verify_event(progress, event, op)
        if self.denied:
            raise OwnershipConflict("Unit original writer denied")
        if isinstance(event, CallCompleted):
            completion = OpenRouterTeacherDecoder().decode(
                self.store.read(event.response.response_ref)
            )
            if completion.skill != event.response.skill:
                raise EvidenceIntegrityError("Original fixture provider skill changed")


@dataclass
class StoredTeacher:
    data: StorageFixture
    native: TeacherRevisionCase
    review: RecordedTeacherRevisionReview
    progress: ConstructionProgress


def stored_teacher(root: Path) -> StoredTeacher:
    root.mkdir()
    data = fixture(root, recorded_teacher=True)
    data.authority = NativeTeacherUnitSourceAuthority(data.store)
    c = revision_case(root / "teacher", construction=data)
    readonly = ReadOnlyEvidence(root / "evidence")
    review = recorded_teacher_review(
        EvidenceTeacherRevisionPlans(
            {c.plan.revision.request_id: c.plan_ref}, readonly
        ),
        c.policy,
        evidence=readonly,
        controls=c.controls,
        context_authority=c.context,
        counts=WholeWireReview(readonly, c.wire),
    )
    journal = data.journal(teacher_review=review)
    progress = journal.create(data.plan, command())
    while True:
        action = progress.project().next_action
        if action.kind == "revise" and action.candidate_slot == 6:
            break
        event = data.event(progress)
        progress = journal.append(event, progress.revision, event.operation)
    planned = CallPlanned(operation=command(), call=c.plan.call)
    progress = journal.append(planned, progress.revision, planned.operation)
    return StoredTeacher(data, c, review, progress)


def event_for(case: StoredTeacher) -> CallCompleted:
    result = case.native.teacher.revise(
        case.native.plan.revision, case.native.plan.send.operation
    )
    return CallCompleted(operation=command(), response=result)


def test_original_file_history_commits_same_teacher_proof_and_finishes_original_method(
    tmp_path: Path,
) -> None:
    case = stored_teacher(tmp_path / "case")
    event = event_for(case)
    journal = case.data.journal(teacher_review=case.review)
    final = journal.append(event, case.progress.revision, event.operation)
    assert final.project().pending_call is None
    assert final.project().candidates[-1].response == event.response
    assert len(final.project().attempts) == 6
    before = (case.data.root / "journal" / journal.file.name).read_bytes()
    # An exact original committed event is a fact replay, even after source denial.
    case.data.authority.denied = True
    assert journal.append(event, case.progress.revision, event.operation) == final
    assert (case.data.root / "journal" / journal.file.name).read_bytes() == before
    case.data.authority.denied = False
    while final.project().next_action.kind != "complete":
        next_event = case.data.event(final)
        final = journal.append(next_event, final.revision, next_event.operation)
    assert len(final.project().attempts) == 7
    selected = final.project().selection
    assert selected is not None and selected.status == "rejected"
    assert journal.read(command()) == final
    assert len(case.native.transport.calls) == 1 and case.native.counts.calls == 2


def test_new_result_without_proof_consumer_is_refused_without_changing_legacy_history(
    tmp_path: Path,
) -> None:
    case = stored_teacher(tmp_path / "case")
    event = event_for(case)
    journal = case.data.journal()
    before = (case.data.root / "journal" / journal.file.name).read_bytes()
    with pytest.raises(OwnershipConflict, match="proof verifier"):
        journal.append(event, case.progress.revision, event.operation)
    assert (case.data.root / "journal" / journal.file.name).read_bytes() == before
    assert journal.read(command()) == case.progress
    assert len(case.native.transport.calls) == 1


@pytest.mark.parametrize(
    "fault",
    ["skill", "execution_plan", "registered_call", "model", "context", "task", "owner"],
)
def test_original_construction_proof_rejects_rebound_but_wrong_result_or_source(
    tmp_path: Path, fault: str
) -> None:
    case = stored_teacher(tmp_path / "case")
    event = event_for(case)
    progress = case.progress
    result = event.response
    assert isinstance(result, RevisionResult)
    execution_ref = result.execution_ref
    assert execution_ref is not None
    if fault == "skill":
        result = result.model_copy(
            update={"skill": result.skill.model_copy(update={"title": "Different"})}
        )
        event = event.model_copy(update={"response": result})
    elif fault == "execution_plan":
        execution = TeacherRevisionExecution.model_validate_json(
            case.data.store.read(execution_ref)
        )
        other = case.data.store.put(
            b'{"another":"original-plan"}',
            EvidenceMetadata(
                media_type="application/json",
                content_schema="teacher-revision-plan/1",
                visibility="private",
                producer="unit-corruption",
            ),
        )
        execution = execution.model_copy(update={"plan_ref": other})
        replaced = case.data.store.put(
            execution.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="teacher-revision-execution/1",
                visibility="private",
                producer="unit-corruption",
            ),
        )
        event = event.model_copy(
            update={"response": result.model_copy(update={"execution_ref": replaced})}
        )
    elif fault == "registered_call":
        changed = progress.events[-1]
        assert isinstance(changed, CallPlanned)
        changed = changed.model_copy(
            update={
                "call": changed.call.model_copy(
                    update={"request_id": "different-original"}
                )
            }
        )
        progress = progress.model_copy(
            update={"events": (*progress.events[:-1], changed)}
        )
    else:
        plan = progress.plan
        if fault == "model":
            plan = plan.model_copy(
                update={
                    "models": tuple(
                        (
                            m.model_copy(update={"model": "another-model"})
                            if m.role == "teacher"
                            else m
                        )
                        for m in plan.models
                    )
                }
            )
        elif fault == "context":
            from lab_generate_skill.domain.construction_inputs import (
                PublicConstructionContext,
            )

            public = PublicConstructionContext.model_validate_json(
                case.data.store.read(plan.public_context_ref)
            )
            ref = case.data.store.put(
                public.model_copy(update={"context_id": "another-context"})
                .model_dump_json()
                .encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema="public-construction-context/1",
                    visibility="public",
                    producer="unit-corruption",
                ),
            )
            plan = plan.model_copy(update={"public_context_ref": ref})
        elif fault == "task":
            plan = plan.model_copy(
                update={
                    "task": plan.task.model_copy(
                        update={
                            "identity": plan.task.identity.model_copy(
                                update={"site": "shopping"}
                            )
                        }
                    )
                }
            )
        elif fault == "owner":
            plan = plan.model_copy(
                update={
                    "run": plan.run.model_copy(
                        update={
                            "owner": plan.run.owner.model_copy(
                                update={"worker_id": "another-worker"}
                            )
                        }
                    )
                }
            )
        progress = progress.model_copy(update={"plan": plan})
    control = case.native.controls.bind(event.operation)
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
        case.review.verify_construction(
            progress, event, event.operation, control=control
        )
    assert len(case.native.transport.calls) == 1 and case.native.counts.calls == 2


@pytest.mark.parametrize("fault", ["cancel", "timeout", "source_denied"])
def test_construction_stop_preserves_known_teacher_return_without_dispatch_or_commit(
    tmp_path: Path, fault: str
) -> None:
    case = stored_teacher(tmp_path / "case")
    event = event_for(case)
    journal = case.data.journal(teacher_review=case.review)
    before = (case.data.root / "journal" / journal.file.name).read_bytes()
    if fault == "source_denied":
        case.data.authority.denied = True
        expected: type[Exception] = OwnershipConflict
    else:
        switch = CancelSwitch()
        switch.cancelled = fault == "cancel"
        op = event.operation.model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="unit", run_id="run", owner_id="owner"
                ),
                "deadline": datetime.now(timezone.utc)
                + timedelta(seconds=-1 if fault == "timeout" else 60),
            }
        )
        event = event.model_copy(update={"operation": op})
        journal.controls = OperationGuards(SystemClock(), switch)
        expected = OperationStopped
    with pytest.raises(expected):
        journal.append(event, case.progress.revision, event.operation)
    assert (case.data.root / "journal" / journal.file.name).read_bytes() == before
    assert len(case.native.transport.calls) == 1


def test_teacher_commit_ack_loss_reconciles_original_event_without_new_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = stored_teacher(tmp_path / "case")
    event = event_for(case)
    journal = case.data.journal(teacher_review=case.review)
    real_replace = os.replace

    def lost(
        src: str,
        dst: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        real_replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
        raise OSError("Teacher completion committed but acknowledgement lost")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", lost)
        with pytest.raises(ConstructionCommitUnconfirmed) as saved:
            journal.append(event, case.progress.revision, event.operation)
    assert saved.value.event_ref.content_schema == "construction-event/1"
    current = journal.read(command())
    assert current.project().candidates[-1].response == event.response
    cleanup = event.operation.cleanup(
        "teacher-construction-reconcile", now=datetime.now(timezone.utc), seconds=30
    )
    assert journal.append(event, case.progress.revision, cleanup) == current
    assert len(case.native.transport.calls) == 1 and case.native.counts.calls == 2


@pytest.mark.parametrize("value", [None, {}, [], "", 17, True])
def test_wrong_construction_payload_rejected_before_proof_reads(
    tmp_path: Path, value: object
) -> None:
    from typing import cast

    case = stored_teacher(tmp_path / "case")
    event = event_for(case)
    with pytest.raises(ValidationError):
        case.review.verify_construction(
            cast(ConstructionProgress, value),
            event,
            event.operation,
            control=case.native.controls.bind(event.operation),
        )
    assert len(case.native.transport.calls) == 1
