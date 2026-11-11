"""Save original ready Actor work; existing Task lifecycle still owns all effects."""

from dataclasses import dataclass
from lab_generate_skill.domain.construction_task_preparation import ActorPreparation
from lab_generate_skill.domain.construction_preparation import PublishedConstructionStep
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.policies.construction_attempt import original_attempt_intent
from lab_generate_skill.ports.evidence import EvidenceStore
from .construct_targets import ConstructionDeps, verify_ready_construction
from .context_evidence import read_bytes, publish_raw


@dataclass(frozen=True)
class ActorPreparationDeps:
    construction: ConstructionDeps
    evidence: EvidenceStore

    def __post_init__(self) -> None:
        if not isinstance(self.construction, ConstructionDeps) or self.evidence is None:
            raise ValueError("Original construction and CAS required")


class ActorPreparationUnconfirmed(RuntimeError):
    def __init__(
        self,
        request: ActorPreparation,
        phase: str,
        primary: BaseException,
        retained: tuple[EvidenceRef, ...],
    ) -> None:
        self.request, self.phase, self.primary, self.retained = (
            request,
            phase,
            primary,
            retained,
        )
        super().__init__(
            "Actor preparation unconfirmed; preserve refs, never infer task dispatch"
        )


def prepare_actor_step(
    request: ActorPreparation, deps: ActorPreparationDeps
) -> PublishedConstructionStep:
    request = ActorPreparation.model_validate(request)
    retained: list[EvidenceRef] = []
    phase = "admission"
    try:
        d = deps.construction
        control = d.controls.bind(request.operation)
        control.checkpoint()
        progress = d.journal.read(request.operation)
        if progress.plan.run != request.run:
            raise OwnershipConflict("Actor preparation changed original run")
        if progress.revision != request.expected_revision:
            raise RevisionConflict("Actor preparation requires exact original history")
        intent = original_attempt_intent(
            progress, request.task.intent.binding.attempt_id
        )
        if request.task.intent != intent:
            raise OwnershipConflict(
                "Task plan changed ready candidate/claim/context/skill"
            )
        verify_ready_construction(progress, d, request.operation, control)
        d.controls.bind(request.task.operation).checkpoint()
        d.controls.bind(request.completion_operation).checkpoint()
        phase = "original_public_inputs"
        context_ref = progress.plan.public_context_ref
        if (
            context_ref.visibility,
            context_ref.content_schema,
            context_ref.media_type,
        ) != ("public", "public-construction-context/1", "application/json"):
            raise OwnershipConflict("Original public construction context required")
        context = PublicConstructionContext.model_validate_json(
            read_bytes(deps.evidence, context_ref, 4 * 1024**2, control)
        )
        public_ref = progress.plan.task.public_task_ref
        public_task = PublicTask.model_validate_json(
            read_bytes(deps.evidence, public_ref, 4 * 1024**2, control)
        )
        if (
            context.task != public_task
            or context.task.identity != progress.plan.task.identity
            or request.task.evaluation.public_task_ref != public_ref
        ):
            raise OwnershipConflict(
                "Task plan/public context changed original public task"
            )
        candidate = progress.project().candidates[intent.candidate_slot].response.skill
        if request.task.skill_ref.media_type != "application/json":
            raise OwnershipConflict("Original public skill JSON required")
        raw_skill = read_bytes(
            deps.evidence, request.task.skill_ref, 4 * 1024**2, control
        )
        skill = CompactSkill.model_validate_json(raw_skill)
        if skill != candidate or skill.model_dump_json().encode() != raw_skill:
            raise OwnershipConflict("Exact original public candidate skill required")
        step = request.step()
        raw = step.model_dump_json().encode()
        verify_ready_construction(progress, d, request.operation, control)
        phase = "publish_step"
        reference = publish_raw(
            deps.evidence,
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="construction-step-plan/1",
                visibility="private",
                producer="construction-task-preparation-v1",
            ),
            retained,
            control,
        )
        verify_ready_construction(progress, d, request.operation, control)
        return PublishedConstructionStep(reference=reference, step=step)
    except BaseException as error:
        raise ActorPreparationUnconfirmed(
            request, phase, error, tuple(retained)
        ) from error
