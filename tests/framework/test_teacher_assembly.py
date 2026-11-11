"""Original source -> assembled plan -> Teacher once -> original journal proof.

All source/provider/count/fee permissions synthetic. Actual original data format
has its separate retained-read receipt; these tests never invoke paid APIs/sites.
"""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.teacher_assembly import (
    assemble_teacher_revision,
    TeacherAssemblyUnconfirmed,
)
from lab_generate_skill.application.teacher_assembly_review import (
    review_teacher_assembly,
)
from lab_generate_skill.bootstrap.teacher_assembly import assembled_teacher
from lab_generate_skill.bootstrap.teacher_revision import recorded_teacher_review
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
)
from lab_generate_skill.domain.teacher_assembly import (
    TeacherRevisionAssemblyInput,
    TeacherRevisionAssemblyReceipt,
    PublishedTeacherRevisionAssembly,
)
from lab_generate_skill.domain.teacher_revision import BoundTeacherRevisionPlan
from lab_generate_skill.domain.construction import CallCompleted
from lab_generate_skill.domain.construction_inputs import RevisionResult
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.construction import ProgressEvent
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from teacher_assembly_fixtures import assembly_case, AssemblyCase
from teacher_source_admission_fixtures import admit_native_source
from test_run_journal import command


def paid_files(c: AssemblyCase) -> dict[str, bytes]:
    return {
        p.name: p.read_bytes()
        for p in (c.source.data.root / "paid-ledger").iterdir()
        if p.is_file()
    }


def cleanup(c: AssemblyCase) -> OperationContext:
    return c.original.preparation.operation.cleanup(
        "assembly-closed-review", now=datetime.now(timezone.utc), seconds=60
    )


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_native_original_source_to_default_teacher_once_and_original_completion_journal(
    tmp_path: Path, site: str
) -> None:
    from lab_generate_skill.domain.identity import Site

    c = assembly_case(tmp_path / "case", cast(Site, site))
    controls = c.source.controls
    op = c.source.operation
    control = controls.bind(op)
    before = paid_files(c)
    published = assemble_teacher_revision(c.original, c.deps, control=control)
    plan = published.bound.plan
    c.send_authority.expected = plan
    assert (
        plan.call.seed == 42
        and plan.call.candidate_slot == 4
        and plan.call.resample_index == 0
    )
    assert plan.revision.projection_ref == c.source.source.source.allowed_input_ref
    assert plan.send.input_ref == c.original.prepared.selected_input_ref
    assert c.deps.journal.read(op).project().pending_call == plan.call
    assert paid_files(c) == before and not c.transport.calls and c.counts.calls == 2
    admission = admit_native_source(c.source, construction=c.deps.journal)
    teacher = assembled_teacher(
        published,
        c.review,
        plan.preparation.policy,
        ledger=c.ledger,
        transport=c.transport,
        evidence=c.source.data.store,
        controls=controls,
        source_authority=c.send_authority,
        context_authority=c.context,
        counts=c.count_review,
        runs=admission.runs,
        claims=admission.deps.claims,
    )
    result = teacher.revise(plan.revision, op)
    assert (
        isinstance(result, RevisionResult)
        and result.schema_version == "revision-result/2"
    )
    assert (
        result.input_sha256 == plan.call.input_ref.sha256
        and len(c.transport.calls) == 1
    )
    proof = recorded_teacher_review(
        EvidenceTeacherRevisionPlans(
            {plan.revision.request_id: published.bound.reference}, c.source.data.store
        ),
        plan.preparation.policy,
        evidence=c.source.data.store,
        controls=controls,
        context_authority=c.context,
        counts=c.count_review,
    )
    journal = c.source.data.journal(teacher_review=proof)
    progress = journal.read(op)
    event = CallCompleted(
        operation=command("original-assembled-teacher-complete"), response=result
    )
    final = journal.append(event, progress.revision, event.operation)
    assert (
        final.project().pending_call is None
        and final.project().next_action.kind == "execute"
        and final.project().next_action.candidate_slot == 4
    )
    closed = cleanup(c)
    receipt = review_teacher_assembly(
        published,
        replace(c.review, journal=journal),
        closed,
        control=controls.bind(closed),
    )
    assert (
        receipt.event.call == plan.call
        and c.counts.calls == 2
        and len(c.transport.calls) == 1
    )
    # Original registered call is immutable even after later progress.
    old = [r for r in c.source.data.root.glob("journal/*.json")]
    assert old
    with pytest.raises(TeacherAssemblyUnconfirmed):
        assemble_teacher_revision(c.original, c.deps, control=control)
    assert len(c.transport.calls) == 1


@pytest.mark.parametrize("round_number", [2, 3])
def test_original_method_revision_seed_and_all_previous_attempts_are_retained(
    tmp_path: Path, round_number: int
) -> None:
    c = assembly_case(tmp_path / "case", round_number=round_number)
    published = assemble_teacher_revision(
        c.original, c.deps, control=c.source.controls.bind(c.source.operation)
    )
    assert published.bound.plan.revision.teacher_round == round_number
    assert published.bound.plan.call.seed == 42 + round_number - 1
    assert len(c.source.parts) == round_number + 3
    assert not c.transport.calls


@pytest.mark.parametrize("bad", [None, True, 0, "", [], {}])
def test_bad_assembly_input_refuses_before_metadata_or_history_effects(
    tmp_path: Path, bad: object
) -> None:
    c = assembly_case(tmp_path / "case")
    before = c.deps.journal.read(c.source.operation)
    paid = paid_files(c)
    with pytest.raises(ValidationError):
        assemble_teacher_revision(
            cast(TeacherRevisionAssemblyInput, bad),
            c.deps,
            control=c.source.controls.bind(c.source.operation),
        )
    assert (
        c.deps.journal.read(c.source.operation) == before
        and paid_files(c) == paid
        and not c.transport.calls
    )


@pytest.mark.parametrize(
    "fault",
    [
        "budget",
        "ceiling",
        "model",
        "source_request",
        "prepared_bytes",
        "denied",
        "seed",
        "output",
    ],
)
def test_incompatible_original_budget_source_prepared_or_actual_parameters_never_register_call(
    tmp_path: Path, fault: str
) -> None:
    c = assembly_case(
        tmp_path / "case",
        parameter_seed=999 if fault == "seed" else None,
        parameter_output_tokens=18 if fault == "output" else 17,
    )
    original = c.original
    if fault == "budget":
        authorization = original.budget.authorization.model_copy(
            update={"authorization_id": "different-original-authorization"}
        )
        original = original.model_copy(
            update={
                "budget": original.budget.model_copy(
                    update={"authorization": authorization}
                )
            }
        )
    elif fault == "ceiling":
        from lab_generate_skill.domain.budget import Money

        original = original.model_copy(update={"ceiling": Money(units=11)})
    elif fault == "model":
        p = original.preparation
        original = original.model_copy(
            update={
                "preparation": p.model_copy(
                    update={
                        "profile": p.profile.model_copy(
                            update={"model": "different-provider-model"}
                        )
                    }
                )
            }
        )
    elif fault == "source_request":
        original = original.model_copy(
            update={
                "preparation": original.preparation.model_copy(
                    update={"request_id": "different-request"}
                )
            }
        )
    elif fault == "prepared_bytes":
        ref = original.prepared.selected_input_ref
        assert ref is not None
        original = original.model_copy(
            update={
                "prepared": original.prepared.model_copy(
                    update={
                        "selected_input_ref": ref.model_copy(
                            update={
                                "sha256": "0" * 64,
                                "uri": "cas://sha256/" + "0" * 64,
                            }
                        )
                    }
                )
            }
        )
    elif fault == "denied":
        c.authority.denied = True
    before = c.deps.journal.read(c.source.operation)
    files = paid_files(c)
    with pytest.raises((TeacherAssemblyUnconfirmed, ValidationError)):
        assemble_teacher_revision(
            original, c.deps, control=c.source.controls.bind(c.source.operation)
        )
    assert (
        c.deps.journal.read(c.source.operation) == before
        and paid_files(c) == files
        and not c.transport.calls
    )


@pytest.mark.parametrize(
    "fault",
    ["cancel", "read_timeout", "plan_ack_loss", "journal_ack_loss", "receipt_ack_loss"],
)
def test_partial_assembly_retains_known_metadata_and_never_recreates_original_call(
    tmp_path: Path, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = assembly_case(tmp_path / "case")
    store = c.source.data.store
    op = c.source.operation
    control: OperationControl = c.source.controls.bind(op)
    original_read, original_put = store.read, store.put
    original_append = c.deps.journal.append
    if fault == "cancel":

        class Cancelled:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", op.operation_id)

            def wait(self, seconds: float) -> None:
                raise AssertionError("No wait")

        control = Cancelled()
    elif fault == "read_timeout":

        def timed_out(ref: EvidenceRef, control: OperationControl) -> bytes:
            if ref == c.original.source.receipt_ref:
                raise TimeoutError("Original source receipt read timed out")
            return original_read(ref, control)

        monkeypatch.setattr(store, "read", timed_out)
    elif fault == "journal_ack_loss":

        def lost_append(
            event: ProgressEvent, expected_revision: int, operation: OperationContext
        ) -> ConstructionProgress:
            original_append(event, expected_revision, operation)
            raise OSError("Original CallPlanned committed, acknowledgement lost")

        monkeypatch.setattr(c.deps.journal, "append", lost_append)
    else:

        def lost_put(
            raw: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            ref = original_put(raw, metadata, control)
            schema = (
                "teacher-revision-plan/1"
                if fault == "plan_ack_loss"
                else "teacher-revision-assembly/1"
            )
            if metadata.content_schema == schema:
                raise OSError("Original metadata committed, acknowledgement lost")
            return ref

        monkeypatch.setattr(store, "put", lost_put)
    beforepaid = paid_files(c)
    with pytest.raises(TeacherAssemblyUnconfirmed) as saved:
        assemble_teacher_revision(c.original, c.deps, control=control)
    failure = saved.value
    assert (
        failure.primary is failure.__cause__
        and not c.transport.calls
        and paid_files(c) == beforepaid
    )
    if fault in ("journal_ack_loss", "receipt_ack_loss"):
        assert c.deps.journal.read(op).project().pending_call is not None
        with pytest.raises(TeacherAssemblyUnconfirmed):
            assemble_teacher_revision(
                c.original, c.deps, control=c.source.controls.bind(op)
            )
    if fault == "receipt_ack_loss":
        ref = next(
            r
            for r in failure.retained
            if r.content_schema == "teacher-revision-assembly/1"
        )
        receipt = TeacherRevisionAssemblyReceipt.model_validate_json(original_read(ref))
        from lab_generate_skill.domain.teacher_revision import TeacherRevisionPlan

        plan = TeacherRevisionPlan.model_validate_json(original_read(receipt.plan_ref))
        known = PublishedTeacherRevisionAssembly(
            receipt_ref=ref,
            bound=BoundTeacherRevisionPlan(reference=receipt.plan_ref, plan=plan),
        )
        closed = cleanup(c)
        assert (
            review_teacher_assembly(
                known, c.review, closed, control=c.source.controls.bind(closed)
            )
            == receipt
        )
    if fault in ("cancel", "read_timeout"):
        assert failure.retained == ()
