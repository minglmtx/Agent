"""Prepare the public Actor input for one currently pending construction attempt.

No state transitions, actions or model calls. The executor must still hold live
authority, CAS the executing transition and obtain any one-use dispatch permit.
Re-reading revisions detects concurrent changes during preparation, not a lock
on the world after return. Cleanup commands cannot obtain this new-work view.
"""

from lab_generate_skill.ports.construction_actor_admission import (
    ActorAdmissionAuthority,
)

from dataclasses import dataclass
from lab_generate_skill.domain.actor_admission import (
    ActorAdmissionRequest,
    CandidateFacts,
    PreparedActorInput,
)
from lab_generate_skill.domain.actor_inputs import ActorInput
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.ports.actor_admission import (
    CandidateInputs,
)
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.run_journal import RunJournal


@dataclass(frozen=True)
class CandidateAdmissionDeps:
    construction: ConstructionJournal
    runs: RunJournal
    inputs: CandidateInputs
    authority: ActorAdmissionAuthority
    controls: OperationControls
    claims: SourceClaims


def prepare_actor_input(
    request: ActorAdmissionRequest, deps: CandidateAdmissionDeps
) -> PreparedActorInput:
    request = ActorAdmissionRequest.model_validate(request)
    op, read_op, intent = request.operation, request.read_operation, request.intent
    control = deps.controls.bind(op)
    control.checkpoint()
    construction = ConstructionProgress.model_validate(deps.construction.read(read_op))
    snapshot = RunSnapshot.model_validate(deps.runs.read(read_op))
    plan, view = construction.plan, construction.project()
    if (
        view.pending_attempt != intent
        or intent.binding.run != plan.run
        or snapshot.binding != plan.run
    ):
        raise OwnershipConflict(
            "Actor candidate is not the original pending construction attempt"
        )
    run, attempts = snapshot.project()
    attempt = next((a for a in attempts if a.binding == intent.binding), None)
    if (
        run.stage != "running"
        or run.stop_reason is not None
        or attempt is None
        or attempt.stage != "baseline_verified"
        or attempt.stop_reason is not None
    ):
        raise InvalidTransition(
            "Actor input requires a running run and unstopped baseline-verified attempt"
        )
    facts = CandidateFacts.model_validate(
        deps.inputs.load(request.equivalence_ref, request.skill_ref, op)
    )
    eq, source, baseline = facts.equivalence, facts.source, facts.baseline
    if (facts.equivalence_ref, facts.skill_ref) != (
        request.equivalence_ref,
        request.skill_ref,
    ):
        raise OwnershipConflict("Input reader returned facts for another request")
    if (
        eq.source_context_receipt_ref != plan.context_receipt_ref
        or source.public_context_ref != plan.public_context_ref
        or intent.public_context_ref != plan.public_context_ref
    ):
        raise OwnershipConflict(
            "Candidate must compare against the frozen construction context"
        )
    if eq.scope != baseline.scope or (
        eq.scope.owner,
        eq.scope.task,
        eq.scope.attempt_id,
    ) != (intent.binding.run.owner, intent.binding.task, intent.binding.attempt_id):
        raise OwnershipConflict(
            "Candidate facts do not belong to the original writer/task/attempt"
        )
    if (
        facts.task_binding != plan.task
        or facts.context.task.identity != plan.task.identity
        or baseline.spec_ref != plan.task.baseline_ref
    ):
        raise OwnershipConflict("Candidate private task or state specification changed")
    observed = facts.observation.record
    if (observed.task, observed.context_id, observed.attempt_id) != (
        baseline.scope.task,
        baseline.scope.context_id,
        baseline.scope.attempt_id,
    ):
        raise OwnershipConflict(
            "Actor observation differs from its checked initial state"
        )
    if (
        facts.skill.content_digest != intent.skill_digest
        or facts.skill != view.candidates[intent.candidate_slot].response.skill
    ):
        raise OwnershipConflict(
            "Actor skill differs from the selected generated candidate"
        )
    if eq.status != "equivalent" or baseline.status != "ready":
        raise InvalidTransition(
            "Unknown/rejected initial state cannot enter Actor execution"
        )
    recorded = attempt.events[-1].outputs
    if (
        request.equivalence_ref not in recorded
        or eq.candidate_baseline_ref not in recorded
    ):
        raise OwnershipConflict(
            "Baseline-verified event must persist these exact baseline/equivalence facts"
        )
    used_operations = {event.operation.operation_id for event in construction.events}
    used_operations.update(
        entry.event.operation.operation_id for entry in snapshot.entries
    )
    used_operations.update(
        (
            eq.operation.operation_id,
            baseline.operation.operation_id,
            source.operation.operation_id,
        )
    )
    if op.operation_id in used_operations:
        raise OwnershipConflict(
            "Actor admission cannot reuse a recorded operation identity"
        )
    actor_input = ActorInput(
        source_context_id=facts.context.context_id,
        task=facts.context.task,
        skill=facts.skill,
        initial_observation=facts.observation,
    )
    control.checkpoint()
    claim = deps.claims.require(plan.claim_ref, intent.binding, op)
    check_source_claim(claim, plan.claim_ref, plan.run, facts.task_binding)
    control.checkpoint()
    deps.authority.verify(request, facts, construction, snapshot)
    control.checkpoint()
    if (
        ConstructionProgress.model_validate(deps.construction.read(read_op))
        != construction
        or RunSnapshot.model_validate(deps.runs.read(read_op)) != snapshot
    ):
        raise RevisionConflict("Journals changed during Actor input preparation")
    control.checkpoint()
    return PreparedActorInput(
        binding=intent.binding,
        operation=op,
        equivalence_ref=request.equivalence_ref,
        baseline_ref=eq.candidate_baseline_ref,
        run_revision=snapshot.revision,
        construction_revision=construction.revision,
        actor_input=actor_input,
    )
