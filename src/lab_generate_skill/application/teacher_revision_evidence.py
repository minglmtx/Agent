"""Original Teacher byte/receipt/usage verification; no model or writer effects."""

from lab_generate_skill.domain.teacher_revision import (
    BoundTeacherRevisionPlan,
    TeacherCompletion,
    TeacherRevisionExecution,
)
from lab_generate_skill.domain.model_response import ModelSendResult, ModelSendFact
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .context_review import ContextReviewDeps, review_context
from .context_evidence import read_bytes


def review_teacher_input(
    bound: BoundTeacherRevisionPlan,
    deps: ContextReviewDeps,
    *,
    control: OperationControl,
) -> ContextPreparationReceipt:
    plan = bound.plan
    return review_context(
        plan.preparation,
        plan.prepared,
        deps,
        expected_input_ref=plan.send.input_ref,
        control=control,
    )


def read_teacher_execution(
    reference: EvidenceRef, store: EvidenceReader, *, control: OperationControl
) -> TeacherRevisionExecution:
    if (reference.visibility, reference.content_schema, reference.media_type) != (
        "private",
        "teacher-revision-execution/1",
        "application/json",
    ):
        raise EvidenceIntegrityError("Original private Teacher execution required")
    raw = read_bytes(store, reference, 2 * 1024**2, control)
    execution = TeacherRevisionExecution.model_validate_json(raw)
    if execution.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError("Original Teacher execution bytes changed")
    return execution


def original_teacher_response(
    bound: BoundTeacherRevisionPlan,
    result: ModelSendResult,
    store: EvidenceReader,
    *,
    control: OperationControl,
) -> bytes:
    plan = bound.plan
    result = ModelSendResult.model_validate(result)
    fact = result.fact
    if (
        fact.request != plan.send.reservation.request
        or fact.operation != plan.send.operation
        or result.settlement.record.reservation != plan.send.reservation
    ):
        raise EvidenceIntegrityError(
            "Teacher sender returned another original call/fee scope"
        )
    if (
        result.settlement.record.state != "succeeded"
        or fact.charge is None
        or result.settlement.record.exceeded_reservation
    ):
        raise EvidenceIntegrityError(
            "Teacher result has no confirmed original successful fee settlement"
        )
    ref = result.fact_ref
    if (ref.visibility, ref.content_schema, ref.media_type) != (
        "private",
        "model-send-fact/1",
        "application/json",
    ):
        raise EvidenceIntegrityError("Original model send fact reference required")
    raw = read_bytes(store, ref, 128 * 1024, control)
    saved = ModelSendFact.model_validate_json(raw)
    if saved != fact or saved.model_dump_json().encode() != raw:
        raise EvidenceIntegrityError("Teacher original send fact changed")
    proof = fact.proof(ref)
    if not any(e.proof == proof for e in result.settlement.record.events):
        raise EvidenceIntegrityError(
            "Teacher original request record lost provider response proof"
        )
    return read_bytes(
        store, fact.response_ref, plan.send.limits.max_response_bytes, control
    )


def check_teacher_completion(
    bound: BoundTeacherRevisionPlan,
    receipt: ContextPreparationReceipt,
    result: ModelSendResult,
    completion: TeacherCompletion,
) -> None:
    plan = bound.plan
    if (
        completion.provider_request_id != result.fact.provider_request_id
        or completion.charge != result.fact.charge
    ):
        raise EvidenceIntegrityError(
            "Original raw provider identity/charge differs from its recorded fact"
        )
    measured = next(
        c.measurement
        for c in receipt.counts
        if c.measurement.input_ref == plan.send.input_ref
    )
    profile = plan.preparation.profile
    if (
        completion.input_tokens is not None
        and completion.input_tokens
        > measured.upper_bound_tokens + profile.uncounted_overhead
    ):
        raise EvidenceIntegrityError(
            "Observed usage exceeds original frozen input bound; admission must not be rewritten"
        )
    output = completion.output_tokens
    if plan.reasoning_accounting == "separate_reasoning":
        output = (
            output + completion.reasoning_tokens
            if output is not None and completion.reasoning_tokens is not None
            else None
        )
    elif (
        output is not None
        and completion.reasoning_tokens is not None
        and completion.reasoning_tokens > output
    ):
        raise EvidenceIntegrityError(
            "Reasoning usage contradicts original inclusive output accounting"
        )
    if output is not None and output > profile.output_reserve:
        raise EvidenceIntegrityError(
            "Observed total output exceeds original frozen reserve"
        )
    # Reported provider tokens are observations. Do not subtract the already
    # reserved protocol margin again or change the historical count/decision.
    if (
        output is not None
        and completion.input_tokens is not None
        and completion.input_tokens + output > profile.context_window
    ):
        raise EvidenceIntegrityError(
            "Observed complete usage exceeds original model window"
        )
