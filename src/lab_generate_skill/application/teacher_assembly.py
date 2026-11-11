"""Freeze original Teacher metadata then append exactly one original CallPlanned.

Never invokes Teacher, reserves fees or recreates a pending/unknown request.
Uncertain CAS/history commits retain every known reference and original event.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.teacher_assembly import (
    TeacherRevisionAssemblyInput,
    TeacherRevisionAssemblyReceipt,
    PublishedTeacherRevisionAssembly,
)
from lab_generate_skill.domain.teacher_revision import BoundTeacherRevisionPlan
from lab_generate_skill.domain.construction import CallPlanned, ConstructionPlan
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.teacher_assembly import (
    TeacherAssemblyAuthority,
    TeacherWireParameterVerifier,
)
from .teacher_source_review import TeacherSourceReviewDeps, review_teacher_source
from .context_review import ContextReviewDeps, review_context
from .context_evidence import read_bytes, publish_raw
from .teacher_assembly_plan import original_teacher_plan, REVISION_METADATA


@dataclass(frozen=True)
class TeacherAssemblyDeps:
    evidence: EvidenceStore
    journal: ConstructionJournal
    plans: RunPlans
    source: TeacherSourceReviewDeps
    context: ContextReviewDeps
    authority: TeacherAssemblyAuthority
    wire_parameters: TeacherWireParameterVerifier


class TeacherAssemblyUnconfirmed(RuntimeError):
    def __init__(
        self,
        original: TeacherRevisionAssemblyInput,
        phase: str,
        primary: BaseException,
        retained: tuple[EvidenceRef, ...],
        event: CallPlanned | None,
    ) -> None:
        self.original, self.phase, self.primary, self.retained, self.event = (
            original,
            phase,
            primary,
            retained,
            event,
        )
        super().__init__(
            "Original Teacher assembly unresolved; inspect retained metadata/history, do not recreate or send"
        )


def assemble_teacher_revision(
    original: TeacherRevisionAssemblyInput,
    deps: TeacherAssemblyDeps,
    *,
    control: OperationControl,
) -> PublishedTeacherRevisionAssembly:
    original = TeacherRevisionAssemblyInput.model_validate(original)
    retained: list[EvidenceRef] = []
    event = None
    phase = "original_history"
    try:
        control.checkpoint()
        op = original.preparation.operation
        progress = deps.journal.read(op)
        phase = "original_admission"
        deps.authority.verify_build(progress, original, control=control)
        run = deps.plans.load(progress.plan.run, op)
        expected = ConstructionPlan.from_run_plan(
            run,
            progress.plan.run,
            progress.plan.task.identity.task_id,
            claim_ref=progress.plan.claim_ref,
            public_context_ref=progress.plan.public_context_ref,
            context_receipt_ref=progress.plan.context_receipt_ref,
            retrieval_ref=progress.plan.retrieval_ref,
            retrieval_scope=progress.plan.retrieval_scope,
            actor_context_configuration_ref=progress.plan.actor_context_configuration_ref,
        )
        if expected != progress.plan or run.budget is None:
            raise OwnershipConflict(
                "Assembly differs from original paid construction RunPlan"
            )
        role = next(r for r in run.budget.roles if r.role == "teacher")
        if (original.budget.authorization, original.budget.budget_id) != (
            run.budget.authorization,
            role.budget_id,
        ) or original.ceiling.units > role.reservation_ceiling.units:
            raise OwnershipConflict(
                "Assembly changed original authorization/subbudget/role ceiling"
            )
        phase = "original_source"
        source = review_teacher_source(original.source, deps.source, control=control)
        raw = read_bytes(deps.evidence, source.progress_ref, 8 * 1024**2, control)
        if (
            ConstructionProgress.model_validate_json(raw) != progress
            or progress.model_dump_json().encode() != raw
        ):
            raise OwnershipConflict(
                "Source assembly snapshot differs from current original construction; no new call"
            )
        plan, event = original_teacher_plan(progress, source, original)
        phase = "same_prepared_bytes"
        review_context(
            original.preparation,
            original.prepared,
            deps.context,
            expected_input_ref=plan.send.input_ref,
            control=control,
        )
        phase = "wire_parameters"
        parameters = read_bytes(
            deps.evidence,
            plan.send.parameters_ref,
            plan.send.limits.max_parameters_bytes,
            control,
        )
        deps.wire_parameters(parameters, plan)
        # All metadata bounds before first CAS or history side effect.
        original_raw = original.model_dump_json().encode()
        plan_raw = plan.model_dump_json().encode()
        input_meta = EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-revision-assembly-input/1",
            visibility="private",
            producer="teacher-revision-assembly",
        )
        plan_meta = EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-revision-plan/1",
            visibility="private",
            producer="teacher-revision-assembly",
        )
        receipt = TeacherRevisionAssemblyReceipt(
            input_ref=evidence_reference(original_raw, input_meta),
            source_progress_ref=source.progress_ref,
            plan_ref=evidence_reference(plan_raw, plan_meta),
            event=event,
            registered_revision=progress.revision + 1,
        )
        phase = "readback_original_history"
        deps.authority.verify_build(progress, original, control=control)
        if deps.journal.read(op) != progress:
            raise OwnershipConflict("Original construction changed during preparation")
        phase = "publish_original_revision"
        publish_raw(
            deps.evidence,
            plan.revision.model_dump_json().encode(),
            REVISION_METADATA,
            retained,
            control,
        )
        phase = "publish_original_assembly"
        input_ref = publish_raw(
            deps.evidence, original_raw, input_meta, retained, control
        )
        phase = "publish_immutable_plan"
        plan_ref = publish_raw(deps.evidence, plan_raw, plan_meta, retained, control)
        phase = "register_original_call"
        registered = deps.journal.append(event, progress.revision, op)
        if (
            registered.events != (*progress.events, event)
            or registered.plan != progress.plan
        ):
            raise OwnershipConflict(
                "Journal returned a different original call/history"
            )
        if (input_ref, plan_ref, registered.revision) != (
            receipt.input_ref,
            receipt.plan_ref,
            receipt.registered_revision,
        ):
            raise OwnershipConflict(
                "Assembly publication changed preflight references or revision"
            )
        phase = "publish_receipt"
        ref = publish_raw(
            deps.evidence,
            receipt.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="teacher-revision-assembly/1",
                visibility="private",
                producer="teacher-revision-assembly",
            ),
            retained,
            control,
        )
        return PublishedTeacherRevisionAssembly(
            receipt_ref=ref,
            bound=BoundTeacherRevisionPlan(reference=plan_ref, plan=plan),
        )
    except BaseException as error:
        raise TeacherAssemblyUnconfirmed(
            original, phase, error, tuple(retained), event
        ) from error
