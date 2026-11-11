"""Strict persisted task source/command/context/proof boundaries; no model sends."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.teacher_source import (
    publish_teacher_source,
    TeacherSourceUnconfirmed,
)
from lab_generate_skill.application.teacher_source_review import (
    TeacherSourceReviewDeps,
    review_teacher_source,
)
from lab_generate_skill.application.teacher_attempt_authority import (
    NativeTeacherSourceAuthority,
)
from lab_generate_skill.application.task_teacher_source import (
    CompletedTaskTeacherSourceAuthority,
)
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.domain.teacher_source import (
    TeacherSourceBindings,
    TeacherSourceReceipt,
    PublishedTeacherSource,
)
from lab_generate_skill.domain.teacher_input import AllowedTeacherEvidence
from lab_generate_skill.domain.task_teacher import TaskTeacherReceipt
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from task_teacher_source_fixtures import complete_task_source_case
from construction_storage_fixtures import put
from test_run_journal import command


@pytest.fixture(scope="module")
def full(tmp_path_factory: pytest.TempPathFactory) -> Any:
    with pytest.MonkeyPatch.context() as patch:
        c = complete_task_source_case(
            tmp_path_factory.mktemp("task-source") / "case", patch, source_seconds=600
        )
        c.native.client.close(c.tasks[0].task.deps.controls.bind(c.bindings.operation))
        yield c


def read_deps(c: Any, operation: Any) -> TeacherSourceReviewDeps:
    controls = c.tasks[0].task.deps.controls
    return TeacherSourceReviewDeps(
        c.data.store,
        EvidenceObservations(c.data.store, controls),
        EvidenceRetrievalRecords(c.data.store, controls, c.data.retrieval_authority),
        c.authority(operation),
        operation,
    )


@pytest.mark.parametrize("count", [5, 6])
def test_complete_revised_history_five_six_keeps_every_original_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    c = complete_task_source_case(
        tmp_path / "case", monkeypatch, count=count, source_seconds=180
    )
    controls = c.tasks[0].task.deps.controls
    before = c.native.loader.session.calls
    source = publish_teacher_source(
        c.progress, c.bindings, c.deps(), control=controls.bind(c.bindings.operation)
    )
    reviewed = review_teacher_source(
        source,
        read_deps(c, c.bindings.operation),
        control=controls.bind(c.bindings.operation),
    )
    assert len(reviewed.bindings.task_receipt_refs or ()) == before == count
    assert c.native.loader.session.calls == before
    assert tuple(x.part.source.candidate_slot for x in c.parts) == tuple(range(count))
    c.native.client.close(controls.bind(c.bindings.operation))


def test_stored_source_reconstructs_full_task_authority_after_closure_without_registry(
    full: Any,
) -> None:
    c = full
    controls = c.tasks[0].task.deps.controls
    op = c.bindings.operation
    calls = c.native.loader.session.calls
    source = publish_teacher_source(
        c.progress, c.bindings, c.deps(), control=controls.bind(op)
    )
    stored = TeacherSourceReceipt.model_validate_json(
        c.data.store.read(source.receipt_ref)
    )
    assert stored.bindings.task_receipt_refs == tuple(p.receipt_ref for p in c.parts)
    assert stored.bindings.schema_version == "teacher-source-bindings/2"
    closed = op.cleanup(
        "read-stored-task-source", now=datetime.now(timezone.utc), seconds=60
    )
    # A fresh authority has no parts side registry; it resolves only saved refs.
    reviewed = review_teacher_source(
        source, read_deps(c, closed), control=controls.bind(closed)
    )
    assert reviewed == stored and c.native.loader.session.calls == calls
    allowed = AllowedTeacherEvidence.model_validate_json(
        c.data.store.read(source.source.allowed_input_ref)
    )
    assert "task_receipt_refs" not in allowed.model_dump_json()
    assert all(x.scope.context_id == "candidate-context" for x in c.originals)
    assert allowed.scope.context_id == "context"


def test_original_binding1_exact_wire_and_strict_versioned_task_fields(
    full: Any,
) -> None:
    data = full.bindings.model_dump()
    data.pop("task_receipt_refs")
    data["schema_version"] = "teacher-source-bindings/1"
    old = TeacherSourceBindings.model_validate(data)
    raw = old.model_dump_json()
    assert "task_receipt_refs" not in raw
    assert TeacherSourceBindings.model_validate_json(raw).model_dump_json() == raw
    assert old.model_dump(include={"request_id"}) == {"request_id": old.request_id}
    assert (
        TeacherSourceBindings.model_validate_json(full.bindings.model_dump_json())
        == full.bindings
    )
    with pytest.raises(ValidationError):
        TeacherSourceBindings.model_validate({**data, "task_receipt_refs": None})


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "empty",
        "short",
        "long",
        "duplicate",
        "public",
        "schema",
        "media",
        "zero",
        "huge",
        "list",
    ],
)
def test_binding2_ref_contract_never_omits_or_mislabels_task_lineage(
    full: Any, fault: str
) -> None:
    data = full.bindings.model_dump()
    refs = full.bindings.task_receipt_refs
    assert refs is not None
    if fault == "missing":
        data.pop("task_receipt_refs")
    elif fault == "empty":
        data["task_receipt_refs"] = ()
    elif fault == "short":
        data["task_receipt_refs"] = refs[:-1]
    elif fault == "long":
        data["task_receipt_refs"] = refs + refs[:3]
    elif fault == "duplicate":
        data["task_receipt_refs"] = (refs[0],) * 4
    elif fault == "list":
        data["task_receipt_refs"] = list(refs)
    else:
        changes = {
            "public": {"visibility": "public"},
            "schema": {"content_schema": "teacher-attempt-source-receipt/1"},
            "media": {"media_type": "text/plain"},
            "zero": {"size_bytes": 0},
            "huge": {"size_bytes": 512 * 1024 + 1},
        }
        data["task_receipt_refs"] = (
            refs[0].model_copy(update=changes[fault]),
            *refs[1:],
        )
    with pytest.raises(ValidationError):
        TeacherSourceBindings.model_validate(data)


@pytest.mark.parametrize("value", [None, {}, [], "", True, 0])
def test_empty_and_wrong_type_binding_has_no_source_or_task_effect(
    full: Any, value: Any
) -> None:
    c = full
    calls = c.native.loader.session.calls
    with pytest.raises(ValidationError):
        publish_teacher_source(
            c.progress,
            value,
            c.deps(),
            control=c.tasks[0].task.deps.controls.bind(c.bindings.operation),
        )
    assert c.native.loader.session.calls == calls


def test_native_only_authority_explicitly_refuses_persisted_task_binding2(
    full: Any,
) -> None:
    c = full
    op = c.bindings.operation
    authority = NativeTeacherSourceAuthority(
        c.authority(op).original, tuple(p.part for p in c.parts), c.review.native, op
    )
    with pytest.raises(EvidenceIntegrityError, match="cannot ignore"):
        authority.verify_prepare(
            c.progress, c.bindings, control=c.tasks[0].task.deps.controls.bind(op)
        )


@pytest.mark.parametrize(
    "fault", ["order", "foreign-part", "wrong-result", "wrong-command"]
)
def test_source_exact_task_result_order_and_command_binding(
    full: Any, fault: str
) -> None:
    c = full
    data = c.bindings.model_dump()
    refs = c.bindings.task_receipt_refs
    assert refs is not None
    if fault == "order":
        data["task_receipt_refs"] = tuple(reversed(refs))
    elif fault == "foreign-part":
        data["task_receipt_refs"] = (refs[1], refs[0], *refs[2:])
    else:
        receipt = TaskTeacherReceipt.model_validate_json(c.data.store.read(refs[0]))
        original = receipt.original
        if fault == "wrong-result":
            original = original.model_copy(update={"result": c.originals[1].result})
        else:
            original = original.model_copy(
                update={"operation": command("foreign-material-command")}
            )
        changed = receipt.model_copy(update={"original": original})
        ref = put(c.data.store, changed, "task-teacher-receipt/1")
        data["task_receipt_refs"] = (ref, *refs[1:])
    bindings = TeacherSourceBindings.model_validate(data)
    with pytest.raises(TeacherSourceUnconfirmed) as caught:
        publish_teacher_source(
            c.progress,
            bindings,
            c.deps(),
            control=c.tasks[0].task.deps.controls.bind(c.bindings.operation),
        )
    assert caught.value.phase == "authority" and not caught.value.retained


@pytest.mark.parametrize("kind", ["source", "closure", "native"])
def test_revoked_original_rights_cannot_be_replaced_by_task_ref_shape(
    full: Any, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    c = full
    target = (
        c.data.authority
        if kind == "source"
        else (c.tasks[-1].task.phases if kind == "closure" else c.native_authority)
    )
    monkeypatch.setattr(
        target, "closure_denied" if kind == "closure" else "denied", True
    )
    with pytest.raises(TeacherSourceUnconfirmed) as caught:
        publish_teacher_source(
            c.progress,
            c.bindings,
            c.deps(),
            control=c.tasks[0].task.deps.controls.bind(c.bindings.operation),
        )
    assert caught.value.phase == "authority" and not caught.value.retained


@pytest.mark.parametrize(
    "field", ["source_context_receipt_ref", "candidate_baseline_ref", "status", "scope"]
)
def test_original_measured_equivalence_is_required_not_context_relabeling(
    full: Any, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    c = full
    contexts = c.original_source.contexts
    load = contexts.load_equivalence

    def foreign(reference: Any, operation: Any) -> Any:
        result = load(reference, operation)
        value = (
            c.progress.plan.public_context_ref
            if field == "source_context_receipt_ref"
            else (
                c.parts[0].receipt_ref
                if field == "candidate_baseline_ref"
                else (
                    "unknown"
                    if field == "status"
                    else result.scope.model_copy(
                        update={"context_id": "foreign-context"}
                    )
                )
            )
        )
        return result.model_copy(update={field: value})

    monkeypatch.setattr(contexts, "load_equivalence", foreign)
    with pytest.raises(TeacherSourceUnconfirmed) as caught:
        publish_teacher_source(
            c.progress,
            c.bindings,
            c.deps(),
            control=c.tasks[0].task.deps.controls.bind(c.bindings.operation),
        )
    assert caught.value.phase == "authority" and not caught.value.retained


def test_cancellation_before_source_has_no_task_or_publication(
    full: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = full
    control = c.tasks[0].task.deps.controls.bind(c.bindings.operation)
    error = OperationStopped("CANCELLED", "task-source-material")

    def stopped() -> float:
        raise error

    monkeypatch.setattr(control, "checkpoint", stopped)
    with pytest.raises(TeacherSourceUnconfirmed) as caught:
        publish_teacher_source(c.progress, c.bindings, c.deps(), control=control)
    assert caught.value.primary is error and not caught.value.retained


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_partial_source_publication_keeps_original_refs_and_no_task_reexecution(
    full: Any, monkeypatch: pytest.MonkeyPatch, stage: int
) -> None:
    c = full
    store = c.data.store
    original = store.put
    writes = 0
    error = OSError("source stored, acknowledgement lost")

    def put_lost(
        data: bytes,
        metadata: EvidenceMetadata,
        control: Any = None,
        *,
        exchange_id: str | None = None,
    ) -> Any:
        nonlocal writes
        ref = original(data, metadata, control, exchange_id=exchange_id)
        writes += 1
        if writes == stage:
            raise error
        return ref

    calls = c.native.loader.session.calls
    with monkeypatch.context() as patch:
        patch.setattr(store, "put", put_lost)
        with pytest.raises(TeacherSourceUnconfirmed) as caught:
            publish_teacher_source(
                c.progress,
                c.bindings,
                c.deps(),
                control=c.tasks[0].task.deps.controls.bind(c.bindings.operation),
            )
    assert caught.value.primary is error
    assert (
        caught.value.phase
        == ["publish_progress", "publish_allowed", "publish_provenance"][stage - 1]
    )
    assert caught.value.retained and c.native.loader.session.calls == calls
    if stage == 3:
        ref = caught.value.retained[-1]
        receipt = TeacherSourceReceipt.model_validate_json(store.read(ref))
        known = PublishedTeacherSource(receipt_ref=ref, source=receipt.source)
        review_teacher_source(
            known,
            read_deps(c, c.bindings.operation),
            control=c.tasks[0].task.deps.controls.bind(c.bindings.operation),
        )
        assert c.native.loader.session.calls == calls
