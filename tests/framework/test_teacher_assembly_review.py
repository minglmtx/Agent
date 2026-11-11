"""Assembly review reads original facts independently, never reconstructs/sends.

Synthetic source/provider/count/fee rights, as in the assembly module fixture.
"""

from pathlib import Path
from typing import NoReturn
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.teacher_assembly import assemble_teacher_revision
from lab_generate_skill.application.teacher_assembly_review import (
    review_teacher_assembly,
)
from lab_generate_skill.bootstrap.teacher_assembly import assembled_teacher
from lab_generate_skill.domain.teacher_assembly import (
    TeacherRevisionAssemblyInput,
    TeacherRevisionAssemblyReceipt,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from teacher_assembly_fixtures import assembly_case
from test_teacher_assembly import cleanup, paid_files


def forbidden(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("Read-only assembly review must not rebuild/write/send/count")


def test_review_uses_independent_original_facts_without_forward_builder_or_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = assembly_case(tmp_path / "case")
    published = assemble_teacher_revision(
        c.original, c.deps, control=c.source.controls.bind(c.source.operation)
    )
    paid = paid_files(c)
    counts = c.counts.calls
    import lab_generate_skill.application.teacher_assembly_plan as forward
    import lab_generate_skill.application.teacher_assembly as assembly

    monkeypatch.setattr(forward, "original_teacher_plan", forbidden)
    monkeypatch.setattr(assembly, "original_teacher_plan", forbidden)
    monkeypatch.setattr(c.source.data.store, "put", forbidden)
    monkeypatch.setattr(c.deps.journal, "append", forbidden)
    monkeypatch.setattr(c.transport, "send", forbidden)
    op = cleanup(c)
    result = review_teacher_assembly(
        published, c.review, op, control=c.source.controls.bind(op)
    )
    assert result.plan_ref == published.bound.reference
    assert paid_files(c) == paid and c.counts.calls == counts and not c.transport.calls


@pytest.mark.parametrize(
    "fault",
    [
        "revision",
        "source_progress",
        "event_operation",
        "missing_registration",
        "unrelated_operation",
        "forged_input",
    ],
)
def test_review_rejects_rehashed_receipt_or_missing_original_registration(
    tmp_path: Path, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = assembly_case(tmp_path / "case")
    published = assemble_teacher_revision(
        c.original, c.deps, control=c.source.controls.bind(c.source.operation)
    )
    store = c.source.data.store
    receipt = TeacherRevisionAssemblyReceipt.model_validate_json(
        store.read(published.receipt_ref)
    )
    op = cleanup(c)
    if fault == "revision":
        receipt = receipt.model_copy(
            update={"registered_revision": receipt.registered_revision + 1}
        )
    elif fault == "source_progress":
        # Same valid type, different immutable object: a rehash does not establish provenance.
        receipt = receipt.model_copy(
            update={
                "source_progress_ref": receipt.source_progress_ref.model_copy(
                    update={"producer": "different-source"}
                )
            }
        )
    elif fault == "event_operation":
        receipt = receipt.model_copy(
            update={
                "event": receipt.event.model_copy(
                    update={
                        "operation": receipt.event.operation.model_copy(
                            update={"operation_id": "foreign-registered-operation"}
                        )
                    }
                )
            }
        )
    elif fault == "forged_input":
        original = c.original.model_copy(
            update={"reasoning_accounting": "separate_reasoning"}
        )
        ref = store.put(
            original.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="teacher-revision-assembly-input/1",
                visibility="private",
                producer="teacher-revision-assembly",
            ),
        )
        receipt = receipt.model_copy(update={"input_ref": ref})
    elif fault == "missing_registration":
        monkeypatch.setattr(
            c.review.journal, "read", lambda operation: c.source.progress
        )
    else:
        op = op.model_copy(update={"parent_operation_id": "foreign-parent"})
    if fault in ("revision", "source_progress", "event_operation", "forged_input"):
        ref = store.put(
            receipt.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="teacher-revision-assembly/1",
                visibility="private",
                producer="teacher-revision-assembly",
            ),
        )
        published = published.model_copy(update={"receipt_ref": ref})
    paid = paid_files(c)
    with pytest.raises((EvidenceIntegrityError, OwnershipConflict, ValidationError)):
        review_teacher_assembly(
            published, c.review, op, control=c.source.controls.bind(op)
        )
    assert paid_files(c) == paid and not c.transport.calls


@pytest.mark.parametrize(
    "fault",
    ["reserve_scope", "same_reserve_send", "settlement_parent", "zero_ceiling", "role"],
)
def test_assembly_input_rejects_nested_role_operation_and_fee_mismatch(
    tmp_path: Path, fault: str
) -> None:
    c = assembly_case(tmp_path / "case")
    value = c.original.model_dump(mode="json")
    if fault == "reserve_scope":
        value["reserve_operation"]["attempt_id"] = "foreign-attempt"
    elif fault == "same_reserve_send":
        value["reserve_operation"] = value["preparation"]["operation"]
    elif fault == "settlement_parent":
        value["settlement_operation"]["parent_operation_id"] = "foreign-parent"
    elif fault == "zero_ceiling":
        value["ceiling"]["units"] = 0
    else:
        value["preparation"]["profile"]["role"] = "actor"
    before = c.deps.journal.read(c.source.operation)
    paid = paid_files(c)
    with pytest.raises(ValidationError):
        TeacherRevisionAssemblyInput.model_validate_json(json.dumps(value))
    assert c.deps.journal.read(c.source.operation) == before
    assert paid_files(c) == paid and not c.transport.calls


def test_bootstrap_rejects_changed_policy_before_original_teacher_or_paid_sender(
    tmp_path: Path,
) -> None:
    c = assembly_case(tmp_path / "case")
    published = assemble_teacher_revision(
        c.original, c.deps, control=c.source.controls.bind(c.source.operation)
    )
    from teacher_source_admission_fixtures import admit_native_source

    admission = admit_native_source(c.source, construction=c.deps.journal)
    policy = published.bound.plan.preparation.policy
    altered = policy.model_copy(update={"policy_id": "foreign-policy"})
    before = paid_files(c)
    with pytest.raises(ValueError, match="frozen context policy"):
        assembled_teacher(
            published,
            c.review,
            altered,
            ledger=c.ledger,
            transport=c.transport,
            evidence=c.source.data.store,
            controls=c.source.controls,
            source_authority=c.send_authority,
            context_authority=c.context,
            counts=c.count_review,
            runs=admission.runs,
            claims=admission.deps.claims,
        )
    assert paid_files(c) == before and not c.transport.calls
