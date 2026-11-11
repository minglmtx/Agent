"""Pure original method/call/send binding; no permission, I/O or ledger effects."""

from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction import ConstructionCall, CallPlanned
from lab_generate_skill.domain.construction_inputs import RevisionInput
from lab_generate_skill.domain.teacher_assembly import TeacherRevisionAssemblyInput
from lab_generate_skill.domain.teacher_revision import TeacherRevisionPlan
from lab_generate_skill.domain.teacher_source import TeacherSourceReceipt
from lab_generate_skill.domain.generation import RequestIdentity, Reservation
from lab_generate_skill.domain.model_request import ModelSendPlan
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import OwnershipConflict

REVISION_METADATA = EvidenceMetadata(
    media_type="application/json",
    content_schema="revision-input/1",
    visibility="teacher",
    producer="teacher-revision-assembly",
)


def original_teacher_plan(
    progress: ConstructionProgress,
    source: TeacherSourceReceipt,
    original: TeacherRevisionAssemblyInput,
) -> tuple[TeacherRevisionPlan, CallPlanned]:
    progress = ConstructionProgress.model_validate(progress)
    source = TeacherSourceReceipt.model_validate(source)
    original = TeacherRevisionAssemblyInput.model_validate(original)
    action = progress.project().next_action
    prep = original.preparation
    if (
        action.kind != "revise"
        or action.candidate_slot is None
        or action.resample_index != 0
        or action.candidate_slot != source.bindings.teacher_round + 3
    ):
        raise OwnershipConflict(
            "Only the original ready Teacher slot can be assembled; pending/unknown cannot renew"
        )
    if (source.source, source.bindings.request_id, source.bindings.operation) != (
        prep.source,
        prep.request_id,
        prep.operation,
    ):
        raise OwnershipConflict(
            "Assembly changed original complete source/request/operation"
        )
    model = next(m for m in progress.plan.models if m.role == "teacher")
    profile = prep.profile
    if (model.provider, model.model, model.paid, model.model_binding_ref) != (
        profile.provider,
        profile.model,
        profile.paid,
        profile.routing_ref,
    ):
        raise OwnershipConflict(
            "Assembly provider/model/routing differs from original construction model"
        )
    if (prep.scope.owner, prep.scope.task) != (
        progress.plan.run.owner,
        progress.plan.task.identity,
    ):
        raise OwnershipConflict("Assembly changed original construction owner/task")
    revision = RevisionInput(
        request_id=prep.request_id,
        teacher_round=source.bindings.teacher_round,
        seed=progress.plan.method.teacher_seed(source.bindings.teacher_round),
        projection_ref=source.source.allowed_input_ref,
    )
    input_ref = evidence_reference(
        revision.model_dump_json().encode(), REVISION_METADATA
    )
    call = ConstructionCall(
        request_id=revision.request_id,
        role="teacher",
        candidate_slot=action.candidate_slot,
        resample_index=0,
        seed=revision.seed,
        temperature=None,
        model_binding_ref=model.model_binding_ref,
        base_parameters_ref=model.parameters_ref,
        input_ref=input_ref,
        parameters_ref=profile.configuration_ref,
    )
    selected = original.prepared.selected_input_ref
    assert selected is not None
    request = RequestIdentity(
        request_id=revision.request_id,
        authorization_id=original.budget.authorization.authorization_id,
        budget_id=original.budget.budget_id,
        owner=prep.scope.owner,
        task=prep.scope.task,
        attempt_id=None,
        candidate_index=call.candidate_slot,
        revision_index=revision.teacher_round,
        role="teacher",
        logical_index=0,
        provider_id=profile.provider,
        model_id=profile.model,
        input_sha256=selected.sha256,
        parameters_sha256=call.parameters_ref.sha256,
    )
    send = ModelSendPlan(
        reservation=Reservation(
            scope=original.budget, request=request, ceiling=original.ceiling
        ),
        input_ref=selected,
        parameters_ref=call.parameters_ref,
        limits=original.limits,
        reserve_operation=original.reserve_operation,
        operation=prep.operation,
        settlement_operation=original.settlement_operation,
    )
    plan = TeacherRevisionPlan(
        revision=revision,
        call=call,
        preparation=prep,
        prepared=original.prepared,
        send=send,
        reasoning_accounting=original.reasoning_accounting,
    )
    return plan, CallPlanned(operation=prep.operation, call=call)
