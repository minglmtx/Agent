"""Live single-source/claim/Actor policy join; no construction/Teacher semantics."""

from dataclasses import dataclass
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.run_journal import RunSnapshot, AttemptEntry
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    RevisionConflict,
)
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.ports.execution_task import ExecutionTaskSources
from lab_generate_skill.ports.claims import SourceClaims, SourceClaimBodyChecks
from lab_generate_skill.domain.execution_task_source import ClaimedExecutionSourceFacts
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.actor import ActorRunAuthority
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from .actor_context_inputs import actor_context_configuration
from .context_evidence import read_bytes


@dataclass(frozen=True)
class ExecutionTaskActorAdmissionDeps:
    sources: ExecutionTaskSources
    runs: RunJournal
    claims: SourceClaims
    evidence: EvidenceReader
    source: ActorRunAuthority

    def authority(
        self,
        plan: TaskExecutionPlan,
        initialized: InitializedTask,
        prepared: PreparedActorInput,
    ) -> ActorRunAuthority:
        return ExecutionTaskActorAuthority(plan, initialized, prepared, self)


class ExecutionTaskActorAuthority:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        initialized: InitializedTask,
        prepared: PreparedActorInput,
        deps: ExecutionTaskActorAdmissionDeps,
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        self.initialized = InitializedTask.model_validate(initialized)
        self.prepared = PreparedActorInput.model_validate(prepared)
        self.deps = deps
        self._configuration: tuple[EvidenceRef, ActorContextConfiguration] | None = None
        self._published_inputs: tuple[EvidenceRef, ...] | None = None
        if any(v is None for v in vars(deps).values()):
            raise ValueError("Original single Actor source/rights mandatory")
        if (
            self.plan.intent.source_kind != "execution"
            or self.prepared.schema_version != "prepared-actor-input/2"
            or self.prepared.execution_source_ref != self.plan.source_ref
        ):
            raise OwnershipConflict(
                "Single Actor authority requires genuine single source/handoff"
            )

    def verify(
        self, request: ActorRunRequest, trace: TraceSnapshot, control: OperationControl
    ) -> None:
        request, trace = ActorRunRequest.model_validate(
            request
        ), TraceSnapshot.model_validate(trace)
        plan, prepared, initialized, d = (
            self.plan,
            self.prepared,
            self.initialized,
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
                "Single Actor changed original request/trace/handoff"
            )
        control.checkpoint()
        d.source.verify(request, trace, control)
        facts = d.sources.load(plan, plan.read_operation, control)
        snapshot = RunSnapshot.model_validate(d.runs.read(plan.read_operation))
        run, attempts = snapshot.project()
        attempt = next((a for a in attempts if a.binding == prepared.binding), None)
        if snapshot.binding != facts.source.run or facts.source.intent != plan.intent:
            raise OwnershipConflict("Single Actor changed original source/run")
        if (
            run.stage != "running"
            or run.stop_reason is not None
            or attempt is None
            or attempt.stage != "executing"
            or attempt.stop_reason is not None
        ):
            raise InvalidTransition(
                "Single Actor requires running/executing unstopped original task"
            )
        policy = facts.policy
        model = facts.run.models[0]
        if (
            request.task.identity != facts.source.task.identity
            or request.skill != policy.skill
            or request.memory != policy.memory
            or request.context_configuration_ref != policy.actor_context_ref
            or request.candidate_id != policy.candidate_id
            or request.revision_round != policy.revision_round
            or request.parameters_refs
            != (model.parameters_ref,) * policy.max_generations
            or (trace.plan.max_generations, trace.plan.max_interactions)
            != (policy.max_generations, policy.max_interactions)
            or (request.task, request.skill)
            != (prepared.actor_input.task, prepared.actor_input.skill)
            or initialized.baseline_ref != prepared.baseline_ref
            or initialized.equivalence_ref != prepared.equivalence_ref
        ):
            raise OwnershipConflict(
                "Single Actor changed explicit original policy/model/initial facts"
            )
        if self._configuration is None:
            cfg = actor_context_configuration(request, d.evidence, control)
            assert request.context_configuration_ref is not None
            self._configuration = (request.context_configuration_ref, cfg)
        reference, cfg = self._configuration
        if reference != request.context_configuration_ref:
            raise OwnershipConflict("Actor changed original configuration reference")
        require_complete_bytes(reference, cfg.model_dump_json().encode())
        if any(
            p.routing_ref != model.model_binding_ref
            or p.configuration_ref != model.parameters_ref
            or p.provider != model.provider
            or p.model != model.model
            or p.paid != model.paid
            for p in cfg.profiles
        ):
            raise OwnershipConflict(
                "Single Actor context route differs from original frozen model"
            )
        if prepared.run_revision >= len(snapshot.entries):
            raise OwnershipConflict("Single handoff lost original baseline revision")
        baseline = snapshot.entries[prepared.run_revision]
        if (
            not isinstance(baseline, AttemptEntry)
            or baseline.binding != prepared.binding
            or baseline.event.stage != "baseline_verified"
            or not {prepared.baseline_ref, prepared.equivalence_ref}.issubset(
                baseline.event.outputs
            )
        ):
            raise OwnershipConflict(
                "Single handoff changed actual original baseline event"
            )
        active = attempt.events[-1]
        if active.operation != request.operation:
            raise OwnershipConflict("Single Actor executing parent changed")
        publication_refs = []
        for schema, raw in (
            (prepared.schema_version, prepared.model_dump_json().encode()),
            (request.schema_version, request.model_dump_json().encode()),
        ):
            refs = [r for r in active.outputs if r.content_schema == schema]
            if len(refs) != 1:
                raise OwnershipConflict(
                    "Single Actor executing event changed exact allowed input bytes"
                )
            reference = refs[0]
            require_complete_bytes(reference, raw)
            publication_refs.append(reference)
            if self._published_inputs is None and (
                read_bytes(d.evidence, reference, 16 * 1024**2, control) != raw
            ):
                raise OwnershipConflict("Actor publication differs from original input")
        confirmed = tuple(publication_refs)
        if self._published_inputs is not None and self._published_inputs != confirmed:
            raise OwnershipConflict("Actor changed original published references")
        self._published_inputs = confirmed
        if isinstance(facts, ClaimedExecutionSourceFacts) and isinstance(
            d.claims, SourceClaimBodyChecks
        ):
            if facts.claim.reference != plan.intent.binding.claim_ref:
                raise OwnershipConflict("Actor source changed original claim body")
            claim = d.claims.require_source_verified(
                facts.claim, facts.source.run, facts.source.task, plan.read_operation
            )
        else:
            claim = d.claims.require(
                plan.intent.binding.claim_ref, plan.intent.binding, request.operation
            )
        check_source_claim(
            claim, plan.intent.binding.claim_ref, facts.source.run, facts.source.task
        )
        d.source.verify(request, trace, control)
        if (
            d.sources.load(plan, plan.read_operation, control) != facts
            or d.runs.read(plan.read_operation) != snapshot
        ):
            raise RevisionConflict(
                "Single Actor source/run changed during turn admission"
            )
        control.checkpoint()
