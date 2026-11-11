"""Source admission failure leaves original claims/history/request identities intact."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.teacher_source_admission import (
    ConstructionTeacherSourceAuthority,
)
from lab_generate_skill.bootstrap.teacher_source_admission import (
    qualified_native_teacher_source,
)
from lab_generate_skill.domain.construction import CallPlanned, CallUncertain
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
    OperationStopped,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.execution import RunEvent, ExecutionFailure
from lab_generate_skill.domain.run_journal import RunEntry, RunSnapshot
from lab_generate_skill.domain.teacher_source import TeacherSourceBindings
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.construction import ConstructionAuthority
from teacher_native_source_fixtures import native_source_case
from teacher_source_admission_fixtures import admit_native_source, SourceAdmissionCase
from construction_storage_fixtures import put
from test_run_journal import command


def error_stop(snapshot: RunSnapshot, source: SourceAdmissionCase) -> RunEntry:
    parent = snapshot.project()[0].events[-1].operation.operation_id
    failure = ExecutionFailure(
        component_id="controller",
        reason_code="unit-original-run-failure",
        message="Injected original run failure before Teacher source admission",
    )
    reference = put(source.native.data.store, failure, "execution-failure/1")
    return RunEntry(
        event=RunEvent(
            stage="closing",
            operation=command("source-admission-error-stop", cleanup_parent=parent),
            previous_operation_id=parent,
            occurred_at=datetime.now(timezone.utc),
            component_id="controller",
            stop_reason="error",
            primary_error=failure,
            outputs=(reference,),
        )
    )


@pytest.mark.parametrize(
    "fault",
    [
        "claim_denied",
        "context_denied",
        "writer_denied",
        "missing_attempt",
        "unsealed_attempt",
        "stopped",
        "pending",
        "unknown",
        "used_operation",
    ],
)
def test_live_source_refuses_original_permission_closure_or_request_gap_without_replacement(
    tmp_path: Path, fault: str
) -> None:
    c = native_source_case(tmp_path / "case")
    a = admit_native_source(
        c,
        omit_last=fault == "missing_attempt",
        unsealed_last=fault == "unsealed_attempt",
    )
    bindings = c.bindings
    if fault == "claim_denied":
        c.data.claim_authority.denied = True
    elif fault == "context_denied":
        c.data.context_authority.denied_context = True
    elif fault == "writer_denied":
        c.data.authority.denied = True
    elif fault == "stopped":
        old = a.runs.read(c.operation)
        stopping = error_stop(old, a)
        a.runs.append(stopping, old.revision, stopping.event.operation)
    elif fault in ("pending", "unknown"):
        journal = c.data.journal()
        event = c.data.event(c.progress)
        assert isinstance(event, CallPlanned)
        progress = journal.append(event, c.progress.revision, event.operation)
        if fault == "unknown":
            ref = put(c.data.store, {"unknown_request": event.call.request_id})
            uncertain = CallUncertain(
                operation=command("original-source-unknown"),
                request_id=event.call.request_id,
                evidence_ref=ref,
            )
            journal.append(uncertain, progress.revision, uncertain.operation)
        # New source ID is insufficient while the original logical slot is pending/unknown.
        bindings = bindings.model_copy(
            update={"request_id": "changed-source-id-cannot-replay"}
        )
    elif fault == "used_operation":
        used = a.runs.read(c.operation).project()[0].events[-1].operation
        bindings = bindings.model_copy(update={"operation": used})
    before_run = a.runs.read(c.operation)
    before_construction = c.data.journal().read(c.operation)
    claims = c.data.claim_authority.create_calls
    with pytest.raises((OwnershipConflict, InvalidTransition)):
        a.authority.verify_prepare(
            c.progress, bindings, control=c.controls.bind(c.operation)
        )
    assert a.runs.read(c.operation) == before_run
    assert c.data.journal().read(c.operation) == before_construction
    assert c.data.claim_authority.create_calls == claims


@pytest.mark.parametrize(
    "fault", ["foreign_parent", "foreign_owner", "attempt_scope", "foreign_run_binding"]
)
def test_recorded_source_requires_original_parent_and_full_run_ownership(
    tmp_path: Path, fault: str
) -> None:
    c = native_source_case(tmp_path / "case")
    a = admit_native_source(c)
    op = c.operation.cleanup(
        "source-bad-closed-read", now=datetime.now(timezone.utc), seconds=60
    )
    run = c.data.plan.run
    if fault == "foreign_parent":
        op = op.model_copy(update={"parent_operation_id": "foreign-parent"})
    elif fault == "foreign_owner":
        op = op.model_copy(update={"owner_id": "foreign-owner"})
    elif fault == "attempt_scope":
        op = op.model_copy(update={"attempt_id": "foreign-attempt"})
    else:
        run = run.model_copy(update={"submission_key": "different-original-binding"})
    authority = qualified_native_teacher_source(
        run, a.deps, c.parts, c.native_review, op
    )
    before = a.runs.read(c.operation)
    with pytest.raises(OwnershipConflict):
        authority.verify_recorded(
            c.progress, c.bindings, control=c.controls.bind(c.operation)
        )
    assert a.runs.read(c.operation) == before


@pytest.mark.parametrize("bad", [None, True, 0, "", {}, [], "extreme_round"])
def test_bad_source_bindings_refuse_before_original_semantic_permission_or_effects(
    tmp_path: Path, bad: object
) -> None:
    c = native_source_case(tmp_path / "case")
    a = admit_native_source(c)
    if bad == "extreme_round":
        bad = c.bindings.model_copy(update={"teacher_round": 2147483647})
    before = a.runs.read(c.operation)
    reads = c.data.claim_authority.read_calls
    with pytest.raises(ValidationError):
        a.authority.verify_prepare(
            c.progress,
            cast(TeacherSourceBindings, bad),
            control=c.controls.bind(c.operation),
        )
    assert (
        a.runs.read(c.operation) == before
        and c.data.claim_authority.read_calls == reads
    )


@pytest.mark.parametrize(
    "fault", ["cancel", "context_timeout", "run_changes_during_admission"]
)
def test_source_cancel_timeout_and_snapshot_race_preserve_original_cause_without_new_work(
    tmp_path: Path, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = native_source_case(tmp_path / "case")
    a = admit_native_source(c)
    control: OperationControl = c.controls.bind(c.operation)
    expected: type[BaseException]
    if fault == "cancel":

        class Cancelled:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", c.operation.operation_id)

            def wait(self, seconds: float) -> None:
                raise AssertionError("No wait")

        control = Cancelled()
        expected = OperationStopped
    elif fault == "context_timeout":

        def timeout(reference: object, operation: OperationContext) -> None:
            raise TimeoutError("Original qualified source read timed out")

        monkeypatch.setattr(a.deps.contexts, "load_context", timeout)
        expected = TimeoutError
    else:
        original = c.data.authority.verify_plan
        calls = 0

        def close_after_permission(plan: object, operation: OperationContext) -> None:
            nonlocal calls
            from lab_generate_skill.domain.construction import ConstructionPlan

            original(cast(ConstructionPlan, plan), operation)
            calls += 1
            if calls == 2:
                snapshot = a.runs.read(c.operation)
                event = error_stop(snapshot, a)
                a.runs.append(event, snapshot.revision, event.event.operation)

        monkeypatch.setattr(c.data.authority, "verify_plan", close_after_permission)
        expected = RevisionConflict
    before = c.data.journal().read(c.operation)
    before_run = a.runs.read(c.operation)
    with pytest.raises(expected):
        a.authority.verify_prepare(c.progress, c.bindings, control=control)
    assert c.data.journal().read(c.operation) == before
    current = a.runs.read(c.operation)
    if fault == "run_changes_during_admission":
        assert (
            current.entries[:-1] == before_run.entries
            and current.project()[0].stage == "closing"
        )
    else:
        assert current == before_run


def test_source_factory_has_no_missing_claim_or_original_authority_fallback(
    tmp_path: Path,
) -> None:
    c = native_source_case(tmp_path / "case")
    a = admit_native_source(c)
    for deps in (
        replace(a.deps, claims=cast(SourceClaims, None)),
        replace(a.deps, original=cast(ConstructionAuthority, None)),
    ):
        with pytest.raises(ValueError, match="Original construction"):
            ConstructionTeacherSourceAuthority(c.data.plan.run, deps, c.operation)
