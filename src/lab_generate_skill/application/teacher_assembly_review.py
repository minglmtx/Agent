"""Independently check assembly facts after plan/role/history progress.

No forward builder, writer, reserve, model or missing-call reconstruction. Original
source progress remains a prefix even after a Teacher result or later attempt.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.teacher_assembly import (
    PublishedTeacherRevisionAssembly,
    TeacherRevisionAssemblyReceipt,
    TeacherRevisionAssemblyInput,
)
from lab_generate_skill.domain.teacher_revision import TeacherRevisionPlan
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.teacher_assembly import (
    TeacherAssemblyAuthority,
    TeacherWireParameterVerifier,
)
from .teacher_source_review import TeacherSourceReviewDeps, review_teacher_source
from .context_review import ContextReviewDeps, review_context
from .context_evidence import read_bytes
from .teacher_actor_reads import canonical


@dataclass(frozen=True)
class TeacherAssemblyReviewDeps:
    evidence: EvidenceReader
    journal: ConstructionJournal
    plans: RunPlans
    source: TeacherSourceReviewDeps
    context: ContextReviewDeps
    authority: TeacherAssemblyAuthority
    wire_parameters: TeacherWireParameterVerifier


def review_teacher_assembly(
    published: PublishedTeacherRevisionAssembly,
    deps: TeacherAssemblyReviewDeps,
    operation: OperationContext,
    *,
    control: OperationControl,
) -> TeacherRevisionAssemblyReceipt:
    published = PublishedTeacherRevisionAssembly.model_validate(published)
    receipt = canonical(
        published.receipt_ref,
        "teacher-revision-assembly/1",
        TeacherRevisionAssemblyReceipt,
        deps.evidence,
        control,
        256 * 1024,
    )
    original = canonical(
        receipt.input_ref,
        "teacher-revision-assembly-input/1",
        TeacherRevisionAssemblyInput,
        deps.evidence,
        control,
        2 * 1024**2,
    )
    plan = canonical(
        receipt.plan_ref,
        "teacher-revision-plan/1",
        TeacherRevisionPlan,
        deps.evidence,
        control,
        2 * 1024**2,
    )
    op = OperationContext.model_validate(operation)
    send = original.preparation.operation
    if op != send and not (
        op.mode == "cleanup"
        and op.parent_operation_id == send.operation_id
        and (op.run_id, op.owner_id, op.attempt_id, op.allocation_id, op.recovery_ref)
        == (send.run_id, send.owner_id, None, None, None)
    ):
        raise OwnershipConflict(
            "Assembly review requires original command or bounded parent cleanup"
        )
    if (receipt.plan_ref, plan) != (published.bound.reference, published.bound.plan):
        raise EvidenceIntegrityError("Assembly substituted the frozen revision plan")
    source = review_teacher_source(original.source, deps.source, control=control)
    before = canonical(
        source.progress_ref,
        "construction-progress/1",
        ConstructionProgress,
        deps.evidence,
        control,
        8 * 1024**2,
    )
    current = deps.journal.read(op)
    index = len(before.events)
    if (
        receipt.source_progress_ref != source.progress_ref
        or current.plan != before.plan
        or current.events[:index] != before.events
        or len(current.events) <= index
        or current.events[index] != receipt.event
        or receipt.registered_revision != before.revision + 1
    ):
        raise EvidenceIntegrityError(
            "Assembly has no exact original registered call in immutable history"
        )
    run = deps.plans.load(before.plan.run, op)
    if (
        ConstructionPlan.from_run_plan(
            run,
            before.plan.run,
            before.plan.task.identity.task_id,
            claim_ref=before.plan.claim_ref,
            public_context_ref=before.plan.public_context_ref,
            context_receipt_ref=before.plan.context_receipt_ref,
            retrieval_ref=before.plan.retrieval_ref,
            retrieval_scope=before.plan.retrieval_scope,
            actor_context_configuration_ref=before.plan.actor_context_configuration_ref,
        )
        != before.plan
        or run.budget is None
    ):
        raise EvidenceIntegrityError("Assembly changed original construction RunPlan")
    role = next(r for r in run.budget.roles if r.role == "teacher")
    if (original.budget.authorization, original.budget.budget_id) != (
        run.budget.authorization,
        role.budget_id,
    ) or original.ceiling.units > role.reservation_ceiling.units:
        raise EvidenceIntegrityError(
            "Assembly changed original authorization/budget or role ceiling"
        )
    action = before.project().next_action
    model = next(m for m in before.plan.models if m.role == "teacher")
    call = plan.call
    prep = plan.preparation
    reservation = plan.send.reservation
    if (
        action.kind != "revise"
        or (call.candidate_slot, call.resample_index, call.seed)
        != (
            action.candidate_slot,
            0,
            before.plan.method.teacher_seed(source.bindings.teacher_round),
        )
        or (call.model_binding_ref, call.base_parameters_ref)
        != (model.model_binding_ref, model.parameters_ref)
    ):
        raise EvidenceIntegrityError(
            "Assembly changed original method/model/base parameter binding"
        )
    if (
        prep,
        plan.prepared,
        plan.send.limits,
        plan.send.reserve_operation,
        plan.send.settlement_operation,
        plan.reasoning_accounting,
        reservation.scope,
        reservation.ceiling,
    ) != (
        original.preparation,
        original.prepared,
        original.limits,
        original.reserve_operation,
        original.settlement_operation,
        original.reasoning_accounting,
        original.budget,
        original.ceiling,
    ):
        raise EvidenceIntegrityError(
            "Assembly changed counted input or original send/fee settings"
        )
    if (
        (prep.source, prep.request_id, prep.operation)
        != (source.source, source.bindings.request_id, source.bindings.operation)
        or (prep.scope.owner, prep.scope.task)
        != (before.plan.run.owner, before.plan.task.identity)
        or (model.provider, model.model, model.paid, model.model_binding_ref)
        != (
            prep.profile.provider,
            prep.profile.model,
            prep.profile.paid,
            prep.profile.routing_ref,
        )
    ):
        raise EvidenceIntegrityError(
            "Assembly changed original source/provider identity"
        )
    if receipt.event.call != call or receipt.event.operation != prep.operation:
        raise EvidenceIntegrityError(
            "Assembly event differs from actual original registered call"
        )
    raw = read_bytes(deps.evidence, call.input_ref, 1024**2, control)
    if raw != plan.revision.model_dump_json().encode():
        raise EvidenceIntegrityError("Original registered RevisionInput bytes changed")
    deps.wire_parameters(
        read_bytes(
            deps.evidence,
            call.parameters_ref,
            plan.send.limits.max_parameters_bytes,
            control,
        ),
        plan,
    )
    review_context(
        prep,
        plan.prepared,
        deps.context,
        expected_input_ref=plan.send.input_ref,
        control=control,
    )
    deps.authority.verify_recorded(before, original, plan, control=control)
    control.checkpoint()
    return receipt
