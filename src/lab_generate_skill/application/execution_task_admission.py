"""Genuine actor-only ExecutionWorkload admission for the same task lifecycle.

No ConstructionProgress, generated candidate, Teacher or second execution loop.
The source reader rechecks original RunPlan/context/claim; physical admission is
still mandatory before resources, initial Actor handoff and each live gate.
"""

from typing import Protocol
from lab_generate_skill.domain.task_execution import TaskExecutionPlan, InitializedTask
from lab_generate_skill.domain.task_admission import TaskAdmissionState
from lab_generate_skill.domain.actor_admission import CandidateFacts, PreparedActorInput
from lab_generate_skill.domain.actor_inputs import ActorInput
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    RevisionConflict,
)
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.ports.execution_task import (
    ExecutionTaskSources,
    ExecutionTaskAuthority,
)
from lab_generate_skill.ports.actor_admission import CandidateInputs
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from .context_evidence import read_bytes


class ExecutionAdmissionInputs(Protocol):
    @property
    def source_reader(self) -> ExecutionTaskSources: ...
    @property
    def inputs(self) -> CandidateInputs: ...
    @property
    def runs(self) -> RunJournal: ...
    @property
    def claims(self) -> SourceClaims: ...
    @property
    def authority(self) -> ExecutionTaskAuthority: ...
    @property
    def controls(self) -> OperationControls: ...
    @property
    def evidence(self) -> EvidenceStore: ...


from lab_generate_skill.domain.task_execution_result import TaskFailureContext
from lab_generate_skill.domain.evidence import EvidenceRef


class ExecutionTaskAdmission:
    def failure_context(
        self,
        plan: TaskExecutionPlan,
        failure_type: str,
        references: tuple[EvidenceRef, ...],
    ) -> TaskFailureContext:
        return TaskFailureContext(
            schema_version="task-failure-context/2",
            intent=plan.intent,
            failure_type=failure_type,
            references=references,
        )

    def __init__(self, deps: ExecutionAdmissionInputs) -> None:
        self.deps = deps
        self.original: ExecutionSourceFacts | None = None
        self.state: TaskAdmissionState | None = None

    def _original(
        self, plan: TaskExecutionPlan, state: TaskAdmissionState
    ) -> ExecutionSourceFacts:
        if (
            self.original is None
            or self.state != state
            or state.source_kind != "execution"
            or state.binding != plan.intent.binding
            or plan.intent.source_kind != "execution"
        ):
            raise OwnershipConflict("Original execution source/admission view changed")
        return self.original

    def open(
        self, plan: TaskExecutionPlan, snapshot: RunSnapshot, control: OperationControl
    ) -> TaskAdmissionState:
        if plan.intent.source_kind != "execution":
            raise OwnershipConflict("Execution admission forbids construction plans")
        original = self.deps.source_reader.load(plan, plan.read_operation, control)
        if self.original is not None and self.original != original:
            raise RevisionConflict(
                "Original execution source cannot rebind after an attempt"
            )
        self.original = original
        self.state = TaskAdmissionState(
            source_kind="execution",
            binding=plan.intent.binding,
            max_generations=original.policy.max_generations,
            max_interactions=original.policy.max_interactions,
        )
        return self.state

    def verify_current(
        self,
        plan: TaskExecutionPlan,
        state: TaskAdmissionState,
        snapshot: RunSnapshot,
        operation: OperationContext,
    ) -> None:
        d, original = self.deps, self._original(plan, state)
        control = d.controls.bind(operation)
        control.checkpoint()
        run, _ = snapshot.project()
        if (
            snapshot.binding != original.source.run
            or run.stage != "running"
            or run.stop_reason is not None
        ):
            raise InvalidTransition(
                "Single task requires original running unstopped run"
            )
        claim = d.claims.require(
            plan.intent.binding.claim_ref, plan.intent.binding, operation
        )
        check_source_claim(
            claim,
            plan.intent.binding.claim_ref,
            original.source.run,
            original.source.task,
        )
        if (
            d.source_reader.load(plan, plan.read_operation, control) != original
            or d.runs.read(plan.read_operation) != snapshot
        ):
            raise RevisionConflict(
                "Original execution source/run changed during admission"
            )
        control.checkpoint()

    def verify_resources(
        self,
        plan: TaskExecutionPlan,
        state: TaskAdmissionState,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        self.deps.authority.verify(
            plan, self._original(plan, state), snapshot, reset, control
        )

    def initialize(
        self,
        plan: TaskExecutionPlan,
        state: TaskAdmissionState,
        initialized: InitializedTask,
        snapshot: RunSnapshot,
        control: OperationControl,
    ) -> PreparedActorInput:
        d, original = self.deps, self._original(plan, state)
        if plan.source_ref is None:
            raise OwnershipConflict("Original execution source ref required")
        op = plan.operation.model_copy(
            update={
                "operation_id": plan.operation.operation_id + ".execution-admission"
            }
        )
        self.verify_current(plan, state, snapshot, op)
        facts = CandidateFacts.model_validate(
            d.inputs.load(initialized.equivalence_ref, plan.skill_ref, op)
        )
        eq, baseline, source = facts.equivalence, facts.baseline, facts.source
        actor, policy = initialized.actor, original.policy
        if original.source.schema_version == "execution-task-source/2":
            selected = eq.adoption
            if (
                eq.schema_version != "equivalence-receipt/2"
                or selected is None
                or selected.execution_source_ref != plan.source_ref
                or selected.binding != plan.intent.binding
                or selected.scope != baseline.scope
                or selected.source_context_ref
                != original.source.source_context_receipt_ref
            ):
                raise OwnershipConflict(
                    "Frozen-source Actor requires its exact current initial adoption"
                )
        elif eq.schema_version != "equivalence-receipt/1" or eq.adoption is not None:
            raise OwnershipConflict(
                "Ordinary Actor cannot consume a frozen-source adoption"
            )
        if (
            facts.equivalence_ref != initialized.equivalence_ref
            or facts.skill_ref != plan.skill_ref
            or eq.source_context_receipt_ref
            != original.source.source_context_receipt_ref
            or source != original.context
            or source.public_context_ref != plan.intent.public_context_ref
            or eq.scope != baseline.scope
            or eq.candidate_baseline_ref != initialized.baseline_ref
            or facts.task_binding != original.source.task
            or baseline.spec_ref != original.source.task.baseline_ref
            or (eq.scope.owner, eq.scope.task, eq.scope.attempt_id)
            != (
                plan.intent.binding.run.owner,
                plan.intent.binding.task,
                plan.intent.binding.attempt_id,
            )
            or facts.context.task.identity != original.source.task.identity
            or facts.skill != policy.skill
            or facts.skill.content_digest != plan.intent.skill_digest
        ):
            raise OwnershipConflict(
                "Single Actor input changed original source/task/skill/initial comparison"
            )
        if eq.status != "equivalent" or baseline.status != "ready":
            raise InvalidTransition(
                "Unconfirmed single-task initial state cannot enter Actor"
            )
        attempts = [
            a for a in snapshot.project()[1] if a.binding == plan.intent.binding
        ]
        if (
            len(attempts) != 1
            or attempts[0].stage != "baseline_verified"
            or attempts[0].stop_reason is not None
            or not {initialized.baseline_ref, initialized.equivalence_ref}.issubset(
                attempts[0].events[-1].outputs
            )
        ):
            raise OwnershipConflict(
                "Single Actor requires original baseline-verified facts"
            )
        observed = Observation.model_validate_json(
            read_bytes(d.evidence, actor.initial_observation_ref, 64 * 1024**2, control)
        )
        if (
            (observed.task, observed.context_id, observed.attempt_id)
            != (eq.scope.task, eq.scope.context_id, eq.scope.attempt_id)
            or observed != facts.observation.record
            or actor.operation != plan.operation
            or actor.scope != eq.scope
            or actor.task != facts.context.task
            or actor.skill != policy.skill
            or actor.schema_version != "actor-run-request/2"
            or actor.context_configuration_ref != policy.actor_context_ref
            or actor.candidate_id != policy.candidate_id
            or actor.revision_round != policy.revision_round
            or actor.memory != policy.memory
        ):
            raise OwnershipConflict(
                "Single Actor lost actual allowed observation/policy/identity"
            )
        if op.operation_id in {
            e.event.operation.operation_id for e in snapshot.entries
        } | {
            eq.operation.operation_id,
            baseline.operation.operation_id,
            source.operation.operation_id,
        }:
            raise OwnershipConflict(
                "Single input admission cannot reuse original operation IDs"
            )
        d.authority.verify_initial(plan, original, facts, snapshot, control)
        self.verify_current(plan, state, snapshot, op)
        return PreparedActorInput(
            schema_version="prepared-actor-input/2",
            binding=plan.intent.binding,
            operation=op,
            equivalence_ref=initialized.equivalence_ref,
            baseline_ref=initialized.baseline_ref,
            run_revision=snapshot.revision,
            execution_source_ref=plan.source_ref,
            actor_input=ActorInput(
                source_context_id=facts.context.context_id,
                task=facts.context.task,
                skill=facts.skill,
                initial_observation=facts.observation,
            ),
        )
