"""Live original construction/run/claim binding for each current v2 Actor turn.

Original source/browser/model exclusivity remains a mandatory authority. This
read-only join neither dispatches nor replaces the original trace/once gates.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.run_journal import RunSnapshot, AttemptEntry
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.ports.actor import ActorRunAuthority
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.lifecycle import OperationControl
from .actor_context_inputs import actor_context_configuration
from .context_evidence import read_bytes


@dataclass(frozen=True)
class TaskActorAdmissionDeps:
    construction: ConstructionJournal
    runs: RunJournal
    claims: SourceClaims
    plans: RunPlans
    evidence: EvidenceReader
    source: ActorRunAuthority

    def authority(
        self,
        plan: TaskExecutionPlan,
        initialized: InitializedTask,
        prepared: PreparedActorInput,
    ) -> ActorRunAuthority:
        return ConstructionTaskActorAuthority(plan, initialized, prepared, self)


class ConstructionTaskActorAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        initialized: InitializedTask,
        prepared: PreparedActorInput,
        deps: TaskActorAdmissionDeps,
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        self.initialized = InitializedTask.model_validate(initialized)
        self.prepared = PreparedActorInput.model_validate(prepared)
        self.deps = deps
        if (
            self.plan.intent.source_kind != "construction"
            or self.prepared.schema_version != "prepared-actor-input/1"
        ):
            raise OwnershipConflict(
                "Construction Actor requires its original construction handoff"
            )
        if any(value is None for value in vars(deps).values()):
            raise ValueError("Original task Actor admission dependencies mandatory")

    def verify(
        self, request: ActorRunRequest, trace: TraceSnapshot, control: OperationControl
    ) -> None:
        request = ActorRunRequest.model_validate(request)
        trace = TraceSnapshot.model_validate(trace)
        plan, initialized, prepared, deps = (
            self.plan,
            self.initialized,
            self.prepared,
            self.deps,
        )
        if (
            request.schema_version != "actor-run-request/2"
            or request != initialized.actor
            or request.operation != plan.operation
            or prepared.binding != plan.intent.binding
            or trace.plan.binding != prepared.binding
            or trace.plan.scope != request.scope
            or trace.plan.initial_observation_ref != request.initial_observation_ref
        ):
            raise OwnershipConflict(
                "Task Actor changed original v2 request/intent/trace"
            )
        control.checkpoint()
        deps.source.verify(request, trace, control)
        progress = ConstructionProgress.model_validate(
            deps.construction.read(plan.read_operation)
        )
        snapshot = RunSnapshot.model_validate(deps.runs.read(plan.read_operation))
        run, attempts = snapshot.project()
        if (
            progress.plan.run != plan.intent.binding.run
            or snapshot.binding != progress.plan.run
            or progress.project().pending_attempt != plan.intent
        ):
            raise OwnershipConflict(
                "Actor is not original pending construction attempt"
            )
        attempt = next((a for a in attempts if a.binding == plan.intent.binding), None)
        if (
            run.stage != "running"
            or run.stop_reason is not None
            or attempt is None
            or attempt.stage != "executing"
            or attempt.stop_reason is not None
        ):
            raise InvalidTransition(
                "Actor new turn requires original running/executing unstopped histories"
            )
        loaded = deps.plans.load(progress.plan.run, plan.read_operation)
        expected = ConstructionPlan.from_run_plan(
            loaded,
            progress.plan.run,
            progress.plan.task.identity.task_id,
            claim_ref=progress.plan.claim_ref,
            public_context_ref=progress.plan.public_context_ref,
            context_receipt_ref=progress.plan.context_receipt_ref,
            retrieval_ref=progress.plan.retrieval_ref,
            retrieval_scope=progress.plan.retrieval_scope,
            actor_context_configuration_ref=progress.plan.actor_context_configuration_ref,
        )
        if (
            expected != progress.plan
            or request.memory != loaded.policies.actor_memory
            or (trace.plan.max_generations, trace.plan.max_interactions)
            != (progress.plan.max_actor_generations, progress.plan.max_interactions)
            or len(request.parameters_refs) != trace.plan.max_generations
        ):
            raise OwnershipConflict("Actor changed full original plan/policy/limits")
        config = actor_context_configuration(request, deps.evidence, control)
        actor = next(model for model in loaded.models if model.role == "actor")
        if any(
            profile.routing_ref != actor.model_binding_ref
            or profile.configuration_ref != actor.parameters_ref
            or profile.provider != actor.provider
            or profile.model != actor.model
            or profile.paid != actor.paid
            for profile in config.profiles
        ):
            raise OwnershipConflict(
                "Actor context route/parameters differ from frozen original model"
            )
        if request.revision_round != (
            0 if plan.intent.candidate_slot < 4 else plan.intent.candidate_slot - 3
        ):
            raise OwnershipConflict(
                "Actor revision round differs from original construction slot"
            )
        if (
            (request.task, request.skill)
            != (prepared.actor_input.task, prepared.actor_input.skill)
            or request.skill.content_digest != plan.intent.skill_digest
            or request.skill
            != progress.project().candidates[plan.intent.candidate_slot].response.skill
            or initialized.baseline_ref != prepared.baseline_ref
            or initialized.equivalence_ref != prepared.equivalence_ref
        ):
            raise OwnershipConflict(
                "Actor lost original candidate/public initial admission"
            )
        if prepared.run_revision >= len(snapshot.entries) or not isinstance(
            snapshot.entries[prepared.run_revision], AttemptEntry
        ):
            raise OwnershipConflict(
                "Actor prepared run revision has no original attempt event"
            )
        baseline = snapshot.entries[prepared.run_revision]
        if (
            not isinstance(baseline, AttemptEntry)
            or baseline.binding != prepared.binding
            or baseline.event.stage != "baseline_verified"
            or not {prepared.baseline_ref, prepared.equivalence_ref}.issubset(
                baseline.event.outputs
            )
        ):
            raise OwnershipConflict("Actor original baseline-verified evidence changed")
        active = attempt.events[-1]
        if active.operation != request.operation:
            raise OwnershipConflict("Executing event changed original Actor operation")
        for schema, raw in (
            (prepared.schema_version, prepared.model_dump_json().encode()),
            (request.schema_version, request.model_dump_json().encode()),
        ):
            refs = [ref for ref in active.outputs if ref.content_schema == schema]
            if (
                len(refs) != 1
                or read_bytes(deps.evidence, refs[0], 16 * 1024**2, control) != raw
            ):
                raise OwnershipConflict(
                    "Actor executing event omitted/changed original exact handoff bytes"
                )
        claim = deps.claims.require(
            progress.plan.claim_ref, plan.intent.binding, request.operation
        )
        check_source_claim(
            claim, progress.plan.claim_ref, progress.plan.run, progress.plan.task
        )
        deps.source.verify(request, trace, control)
        claim2 = deps.claims.require(
            progress.plan.claim_ref, plan.intent.binding, request.operation
        )
        check_source_claim(
            claim2, progress.plan.claim_ref, progress.plan.run, progress.plan.task
        )
        if (
            deps.construction.read(plan.read_operation) != progress
            or deps.runs.read(plan.read_operation) != snapshot
        ):
            raise RevisionConflict(
                "Original task histories changed during Actor turn admission"
            )
        control.checkpoint()
