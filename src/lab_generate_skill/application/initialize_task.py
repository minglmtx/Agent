"""Validate measured original initial state and admit exactly its public Actor view."""

from lab_generate_skill.domain.actor_admission import (
    ActorAdmissionRequest,
    PreparedActorInput,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task_execution import InitializedTask, TaskExecutionPlan
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .admit_candidate import CandidateAdmissionDeps, prepare_actor_input
from .context_evidence import read_bytes


def initialize_task(
    plan: TaskExecutionPlan,
    initialized: InitializedTask,
    deps: CandidateAdmissionDeps,
    evidence: EvidenceReader,
    control: OperationControl,
) -> PreparedActorInput:
    """Consume original initialization; never start/reset/observe a second page.

    The live TaskInitialization port has already produced/published the baseline
    and equivalence. This shared join uses the existing full independent reader
    and original candidate admission after baseline_verified was committed.
    """
    plan = TaskExecutionPlan.model_validate(plan)
    initialized = InitializedTask.model_validate(initialized)
    actor, intent = initialized.actor, plan.intent
    scope = actor.scope
    if (
        scope.owner,
        scope.task,
        scope.attempt_id,
        actor.operation,
        actor.skill.content_digest,
    ) != (
        intent.binding.run.owner,
        intent.binding.task,
        intent.binding.attempt_id,
        plan.operation,
        intent.skill_digest,
    ):
        raise OwnershipConflict(
            "Initialized Actor changed original task/attempt/skill/operation"
        )
    operation = plan.operation.model_copy(
        update={"operation_id": plan.operation.operation_id + ".candidate-admission"}
    )
    prepared = prepare_actor_input(
        ActorAdmissionRequest(
            intent=intent,
            equivalence_ref=initialized.equivalence_ref,
            skill_ref=plan.skill_ref,
            operation=operation,
            read_operation=plan.read_operation,
        ),
        deps,
    )
    public = prepared.actor_input
    observed = Observation.model_validate_json(
        read_bytes(evidence, actor.initial_observation_ref, 64 * 1024**2, control)
    )
    if (
        prepared.baseline_ref,
        public.task,
        public.skill,
        public.initial_observation.record,
        public.initial_observation.record.context_id,
    ) != (
        initialized.baseline_ref,
        actor.task,
        actor.skill,
        observed,
        scope.context_id,
    ):
        raise OwnershipConflict(
            "Actor request differs from the measured original public admission"
        )
    return prepared
