"""Scoped immutable transaction reads; original Teacher verifier stays mandatory."""

from datetime import datetime, timedelta, timezone
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.bootstrap.teacher_transaction_review import (
    transaction_teacher_review,
)
from lab_generate_skill.domain.construction import CallCompleted
from lab_generate_skill.domain.construction_inputs import RevisionResult
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.teacher_revision import TeacherCompletion
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_construction_state import (
    initial,
    advance,
    completed_call,
    ref,
    append,
    planned_call,
)
from test_run_journal import command, CancelSwitch


def original_result() -> tuple[ConstructionProgress, CallCompleted]:
    progress = initial()
    for _ in range(12):
        if progress.project().next_action.kind == "revise":
            progress = append(progress, planned_call(progress))
            event = completed_call(progress)
            result = RevisionResult.model_validate(
                event.response.model_copy(
                    update={
                        "schema_version": "revision-result/2",
                        "execution_ref": ref(
                            "original-execution", "teacher-revision-execution/1"
                        ),
                    }
                )
            )
            return progress, CallCompleted(operation=event.operation, response=result)
        progress = advance(progress)
    raise AssertionError("Original mandatory first Teacher revision was not ready")


def test_transaction_view_checks_exact_scope_is_readonly_and_reuses_original_verifier() -> (
    None
):
    progress, event = original_result()
    controls = OperationGuards(SystemClock(), CancelSwitch())
    read_op = command("transaction-snapshot-read", cleanup_parent="original-source")
    calls: list[CallCompleted] = []

    expected_progress, expected_event = progress, event

    def bind(snapshot: ConstructionJournal) -> TeacherConstructionVerifier:
        assert snapshot.read(read_op) == progress
        with pytest.raises(OwnershipConflict):
            snapshot.read(read_op.model_copy(update={"operation_id": "different-read"}))
        with pytest.raises(OwnershipConflict, match="read-only"):
            snapshot.create(progress.plan, read_op)
        with pytest.raises(OwnershipConflict, match="read-only"):
            snapshot.append(event, progress.revision, read_op)

        class Original:
            def verify_construction(
                self,
                progress: ConstructionProgress,
                event: CallCompleted,
                operation: OperationContext,
                *,
                control: OperationControl,
            ) -> TeacherCompletion:
                assert (
                    progress == expected_progress
                    and event == expected_event
                    and operation == event.operation
                )
                control.checkpoint()
                calls.append(event)
                return TeacherCompletion(
                    provider_request_id="original-provider",
                    skill=event.response.skill,
                    charge=None,
                )

        return Original()

    review = transaction_teacher_review(bind, read_op, controls=controls)
    one = review.verify_construction(
        progress, event, event.operation, control=controls.bind(event.operation)
    )
    two = review.verify_construction(
        progress, event, event.operation, control=controls.bind(event.operation)
    )
    assert one == two and calls == [event, event]


@pytest.mark.parametrize("bad", [None, True, 0, {}, []])
def test_transaction_bad_progress_never_invokes_proof_or_mutates_state(
    bad: object,
) -> None:
    progress, event = original_result()
    controls = OperationGuards(SystemClock(), CancelSwitch())

    def forbidden(snapshot: ConstructionJournal) -> TeacherConstructionVerifier:
        raise AssertionError("Malformed input must not reach original proof")

    review = transaction_teacher_review(
        forbidden, command("snapshot-read"), controls=controls
    )
    with pytest.raises(ValidationError):
        review.verify_construction(
            cast(ConstructionProgress, bad),
            event,
            event.operation,
            control=controls.bind(event.operation),
        )
    assert progress.project().pending_call is not None


@pytest.mark.parametrize(
    "fault",
    [
        "legacy_result",
        "wrong_owner",
        "attempt_scope",
        "expired_read",
        "cancel",
        "missing_proof",
    ],
)
def test_transaction_role_scope_deadline_cancel_and_missing_proof_refuse(
    fault: str,
) -> None:
    progress, event = original_result()
    controls = OperationGuards(SystemClock(), CancelSwitch())
    read_op = command("snapshot-read")
    expected: type[BaseException] = OwnershipConflict
    control: OperationControl = controls.bind(event.operation)
    reached: list[bool] = []
    if fault == "legacy_result":
        event = completed_call(progress)
    elif fault == "wrong_owner":
        read_op = read_op.model_copy(update={"owner_id": "foreign-owner"})
    elif fault == "attempt_scope":
        read_op = read_op.model_copy(update={"attempt_id": "foreign-attempt"})
    elif fault == "expired_read":
        read_op = read_op.model_copy(
            update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        expected = OperationStopped
    elif fault == "cancel":

        class Cancelled:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", event.operation.operation_id)

            def wait(self, seconds: float) -> None:
                raise AssertionError("No wait")

        control = Cancelled()
        expected = OperationStopped
    else:
        expected = ValueError

    def missing(snapshot: ConstructionJournal) -> TeacherConstructionVerifier:
        reached.append(True)
        return cast(TeacherConstructionVerifier, None)

    review = transaction_teacher_review(missing, read_op, controls=controls)
    with pytest.raises(expected):
        review.verify_construction(progress, event, event.operation, control=control)
    assert reached == ([True] if fault == "missing_proof" else [])


def test_transaction_propagates_original_proof_failure_unchanged() -> None:
    progress, event = original_result()
    controls = OperationGuards(SystemClock(), CancelSwitch())
    primary = EvidenceIntegrityError("Original complete proof rejected")

    class Reject:
        def verify_construction(
            self,
            progress: ConstructionProgress,
            event: CallCompleted,
            operation: OperationContext,
            *,
            control: OperationControl,
        ) -> TeacherCompletion:
            raise primary

    review = transaction_teacher_review(
        lambda snapshot: Reject(), command("snapshot-read"), controls=controls
    )
    with pytest.raises(EvidenceIntegrityError) as saved:
        review.verify_construction(
            progress, event, event.operation, control=controls.bind(event.operation)
        )
    assert saved.value is primary
