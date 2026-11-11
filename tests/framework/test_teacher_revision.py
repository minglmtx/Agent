"""Original Teacher port + actual budget ledger; source/provider/byte tokens fake."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.bootstrap.teacher_revision import recorded_teacher_review
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
)
from lab_generate_skill.application.teacher_revision import (
    TeacherRevisionUnconfirmed,
    TeacherRevisionResponseRejected,
)
from lab_generate_skill.domain.construction_inputs import RevisionResult
from lab_generate_skill.domain.construction import CallCompleted
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.model_response import ModelSendUnconfirmed
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.teacher_revision import (
    TeacherRevisionPlan,
    TeacherRevisionExecution,
)
from lab_generate_skill.ports.teacher import Teacher
from source_review_records import ReadOnlyEvidence
from teacher_revision_fixtures import revision_case, WholeWireReview


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_original_teacher_port_same_saved_input_once_sender_and_independent_revision_export_review(
    tmp_path: Path, site: Site
) -> None:
    c = revision_case(tmp_path / "case", site)
    teacher: Teacher = c.teacher
    result = teacher.revise(c.plan.revision, c.plan.send.operation)
    assert (
        result.schema_version == "revision-result/2"
        and result.execution_ref is not None
    )
    assert result.input_sha256 == c.plan.call.input_ref.sha256
    assert result.input_sha256 != c.plan.send.input_ref.sha256
    assert result.response_ref.content_schema == "teacher-model-response/1"
    assert len(c.transport.calls) == 1 and c.counts.calls == 2
    assert c.source.calls == 2
    assert c.transport.calls[0].input_bytes == c.store.read(c.plan.send.input_ref)
    execution = TeacherRevisionExecution.model_validate_json(
        c.store.read(result.execution_ref)
    )
    assert (
        execution.plan_ref == c.plan_ref
        and execution.send_result.fact.response_ref == result.response_ref
    )
    assert execution.send_result.settlement.record.state == "succeeded"
    assert execution.send_result.settlement.record.charged.units == 2
    event = CallCompleted(operation=c.plan.send.operation, response=result)
    assert CallCompleted.model_validate_json(event.model_dump_json()) == event
    record = c.ledger.read(
        c.plan.send.reservation.request, c.plan.send.settlement_operation
    )
    assert [e.state for e in record.events] == [
        "budget_reserved",
        "dispatching",
        "succeeded",
    ]
    readonly = ReadOnlyEvidence(tmp_path / "case/evidence")
    plans = EvidenceTeacherRevisionPlans({result.request_id: c.plan_ref}, readonly)
    counts = WholeWireReview(readonly, c.wire)
    reviewer = recorded_teacher_review(
        plans,
        c.policy,
        evidence=readonly,
        controls=c.controls,
        context_authority=c.context,
        counts=counts,
    )
    completion = reviewer.verify(
        c.plan.revision, result, c.plan.send.settlement_operation
    )
    assert (
        completion.skill == result.skill
        and completion.charge is not None
        and completion.charge.units == 2
    )
    assert completion.input_tokens == 100 and completion.reasoning_tokens == 2
    assert (
        len(c.transport.calls) == 1
        and c.counts.calls == 2
        and not hasattr(counts, "measure")
    )
    with pytest.raises(ModelSendUnconfirmed):
        teacher.revise(c.plan.revision, c.plan.send.operation)
    assert len(c.transport.calls) == 1


def test_legacy_teacher_revision_v1_exact_shape_and_explicit_new_version_fields(
    tmp_path: Path,
) -> None:
    c = revision_case(tmp_path / "case")
    reply_ref = c.store.put(
        c.transport.reply_bytes,
        EvidenceMetadata(
            media_type="application/octet-stream",
            content_schema="teacher-model-response/1",
            visibility="private",
            producer="unit-response-shape-only",
        ),
    )
    # Explicit old DTO shape, in the original CandidateResponse field order.
    raw = json.dumps(
        dict(
            request_id="original-legacy",
            input_sha256="a" * 64,
            parameters_sha256="b" * 64,
            skill={
                "schema_version": "compact-skill/1",
                "title": "Preserve source",
                "principle": "Read the complete evidence.",
                "when_to_apply": "When revising a failed attempt.",
            },
            response_ref=reply_ref.model_dump(mode="json"),
            schema_version="revision-result/1",
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    old = RevisionResult.model_validate_json(raw)
    assert (
        old.model_dump_json().encode() == raw
        and RevisionResult.model_validate(old) == old
    )
    with pytest.raises(ValueError):
        RevisionResult.model_validate({**old.model_dump(), "execution_ref": None})
    with pytest.raises(ValueError):
        RevisionResult.model_validate(
            {**old.model_dump(), "schema_version": "revision-result/2"}
        )


def test_new_ID_format_or_operation_cannot_reuse_original_teacher_binding(
    tmp_path: Path,
) -> None:
    c = revision_case(tmp_path / "case")
    for request in (
        c.plan.revision.model_copy(update={"request_id": "new-id"}),
        c.plan.revision.model_copy(
            update={
                "projection_ref": c.plan.revision.projection_ref.model_copy(
                    update={"sha256": "e" * 64}
                )
            }
        ),
    ):
        with pytest.raises(OwnershipConflict):
            c.teacher.revise(request, c.plan.send.operation)
    with pytest.raises(OwnershipConflict):
        c.teacher.revise(c.plan.revision, c.plan.send.settlement_operation)
    assert len(c.transport.calls) == 0


@pytest.mark.parametrize(
    "field",
    [
        "model",
        "input",
        "fee",
        "source",
        "round",
        "call_hash",
        "parameters",
        "prepared",
        "operation",
    ],
)
def test_revision_plan_refuses_mismatched_original_links_before_send(
    tmp_path: Path, field: str
) -> None:
    c = revision_case(tmp_path / "case")
    value = c.plan.model_dump()
    if field == "model":
        value["send"]["reservation"]["request"]["model_id"] = "foreign"
    elif field == "input":
        value["prepared"]["selected_input_ref"] = None
    elif field == "fee":
        value["preparation"]["profile"]["fee_scope_ref"]["sha256"] = "f" * 64
    elif field == "source":
        value["revision"]["projection_ref"]["sha256"] = "f" * 64
    elif field == "round":
        value["revision"]["teacher_round"] = 2
    elif field == "call_hash":
        value["call"]["input_ref"]["sha256"] = "f" * 64
    elif field == "parameters":
        value["call"]["parameters_ref"]["sha256"] = "f" * 64
    elif field == "prepared":
        value["prepared"]["request_sha256"] = "f" * 64
    else:
        value["send"]["operation"]["operation_id"] = "foreign"
    with pytest.raises((ValueError, OwnershipConflict)):
        TeacherRevisionPlan.model_validate(value)
    assert len(c.transport.calls) == 0


def test_original_unknown_dispatch_is_not_replayed_under_same_or_new_ID(
    tmp_path: Path,
) -> None:
    c = revision_case(tmp_path / "case")
    c.transport.error = TimeoutError("original unknown HTTP operation")
    for _ in range(2):
        with pytest.raises(ModelSendUnconfirmed):
            c.teacher.revise(c.plan.revision, c.plan.send.operation)
    with pytest.raises(OwnershipConflict):
        c.teacher.revise(
            c.plan.revision.model_copy(update={"request_id": "new-id"}),
            c.plan.send.operation,
        )
    assert len(c.transport.calls) == 1
    record = c.ledger.read(
        c.plan.send.reservation.request, c.plan.send.settlement_operation
    )
    assert record.state == "dispatching" and record.held.units == 4


@pytest.mark.parametrize(
    "fault",
    [
        "bad_skill",
        "partial_completion",
        "wrong_provider",
        "wrong_charge",
        "prompt_overrun",
        "output_overrun",
        "unknown_charge",
    ],
)
def test_original_return_and_ledger_facts_survive_response_usage_or_charge_failures(
    tmp_path: Path, fault: str
) -> None:
    c = revision_case(tmp_path / "case")
    body = json.loads(c.transport.reply_bytes)
    if fault == "bad_skill":
        body["choices"][0]["message"]["content"] = '{"title":"only title"}'
    elif fault == "partial_completion":
        body["choices"][0]["finish_reason"] = "length"
    elif fault == "wrong_provider":
        body["id"] = "another-provider-request"
    elif fault == "wrong_charge":
        body["usage"]["cost"] = 3e-9
    elif fault == "prompt_overrun":
        body["usage"]["prompt_tokens"] = 100001
    elif fault == "output_overrun":
        body["usage"]["completion_tokens"] = 18
    else:
        c.transport.charge = None
    c.transport.reply_bytes = json.dumps(body, separators=(",", ":")).encode()
    with pytest.raises(TeacherRevisionUnconfirmed) as caught:
        c.teacher.revise(c.plan.revision, c.plan.send.operation)
    error = caught.value
    assert len(c.transport.calls) == 1 and error.returned.fact.response_ref is not None
    assert c.store.read(error.returned.fact.response_ref) == c.transport.reply_bytes
    assert any(
        ref.content_schema == "teacher-revision-execution/1" for ref in error.retained
    )
    assert error.returned.settlement.record.state == (
        "uncertain" if fault == "unknown_charge" else "succeeded"
    )


def test_source_denial_and_cancel_before_original_send_have_no_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.domain.errors import OperationStopped
    from lab_generate_skill.domain.lifecycle import OperationContext
    from lab_generate_skill.ports.lifecycle import OperationControl

    c = revision_case(tmp_path / "case")
    c.source.denied = True
    with pytest.raises(OwnershipConflict):
        c.teacher.revise(c.plan.revision, c.plan.send.operation)
    assert len(c.transport.calls) == 0 and c.counts.calls == 2
    c.source.denied = False

    class Stopped:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "original-teacher")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    def cancel(op: OperationContext) -> OperationControl:
        return Stopped()

    monkeypatch.setattr(c.controls, "bind", cancel)
    with pytest.raises(OperationStopped):
        c.teacher.revise(c.plan.revision, c.plan.send.operation)
    assert len(c.transport.calls) == 0


def test_execution_commit_ack_loss_retains_original_return_and_allows_only_readonly_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.ports.lifecycle import OperationControl

    c = revision_case(tmp_path / "case")
    original_put = c.store.put

    def lose(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        ref = original_put(data, metadata, control, exchange_id=exchange_id)
        if metadata.content_schema == "teacher-revision-execution/1":
            raise TimeoutError("original execution CAS acknowledgement lost")
        return ref

    monkeypatch.setattr(c.store, "put", lose)
    with pytest.raises(TeacherRevisionUnconfirmed) as caught:
        c.teacher.revise(c.plan.revision, c.plan.send.operation)
    error = caught.value
    assert error.stage == "save_original_return" and len(c.transport.calls) == 1
    assert error.returned.settlement.record.state == "succeeded"
    ref = next(
        r for r in error.retained if r.content_schema == "teacher-revision-execution/1"
    )
    saved = TeacherRevisionExecution.model_validate_json(c.store.read(ref))
    assert saved.send_result == error.returned
    # Resolve only the original saved response/execution; no Teacher.revise or
    # transport operation is involved in reconstructing the immutable result.
    from lab_generate_skill.adapters.models.teacher_response import (
        OpenRouterTeacherDecoder,
    )

    completion = OpenRouterTeacherDecoder().decode(
        c.store.read(error.returned.fact.response_ref)
    )
    result = RevisionResult(
        schema_version="revision-result/2",
        request_id=c.plan.revision.request_id,
        input_sha256=c.plan.call.input_ref.sha256,
        parameters_sha256=c.plan.call.parameters_ref.sha256,
        skill=completion.skill,
        response_ref=error.returned.fact.response_ref,
        execution_ref=ref,
    )
    readonly = ReadOnlyEvidence(tmp_path / "case/evidence")
    plans = EvidenceTeacherRevisionPlans({result.request_id: c.plan_ref}, readonly)
    review = recorded_teacher_review(
        plans,
        c.policy,
        evidence=readonly,
        controls=c.controls,
        context_authority=c.context,
        counts=WholeWireReview(readonly, c.wire),
    )
    assert (
        review.verify(c.plan.revision, result, c.plan.send.settlement_operation)
        == completion
    )
    assert len(c.transport.calls) == 1


def test_readonly_export_refuses_rebound_skill_or_native_response_reference(
    tmp_path: Path,
) -> None:
    c = revision_case(tmp_path / "case")
    result = c.teacher.revise(c.plan.revision, c.plan.send.operation)
    readonly = ReadOnlyEvidence(tmp_path / "case/evidence")
    plans = EvidenceTeacherRevisionPlans({result.request_id: c.plan_ref}, readonly)
    reviewer = recorded_teacher_review(
        plans,
        c.policy,
        evidence=readonly,
        controls=c.controls,
        context_authority=c.context,
        counts=WholeWireReview(readonly, c.wire),
    )
    for change in (
        {"input_sha256": c.plan.send.input_ref.sha256},
        {"parameters_sha256": "f" * 64},
        {"response_ref": result.response_ref.model_copy(update={"sha256": "f" * 64})},
        {
            "skill": result.skill.model_copy(
                update={"principle": "A changed exported principle."}
            )
        },
    ):
        with pytest.raises(EvidenceIntegrityError):
            reviewer.verify(
                c.plan.revision,
                result.model_copy(update=change),
                c.plan.send.settlement_operation,
            )
    assert len(c.transport.calls) == 1
