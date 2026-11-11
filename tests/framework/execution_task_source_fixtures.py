"""Genuine actor-only CAS/claim/run/source; explicit synthetic resource rights.

Creates no ConstructionPlan, ConstructionProgress, Generator or Teacher result.
This exercises software provenance/lifecycle, never actual Map qualification.
"""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.bootstrap.execution_task_source import (
    publish_execution_task_source,
)
from lab_generate_skill.domain.initial_equivalence import EquivalenceInputs
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.execution import RunBinding, AttemptBinding
from lab_generate_skill.domain.execution_task_source import (
    ExecutionTaskInputs,
    ExecutionTaskSource,
    ExecutionSourceFacts,
)
from lab_generate_skill.domain.actor_admission import CandidateFacts
from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.optional_policies import RunPolicies, InactivePolicy
from lab_generate_skill.domain.run_plan import (
    RunPlan,
    RunResources,
    RoleModelPlan,
    ExecutionWorkload,
)
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.task_intent import TaskAttemptIntent
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from context_storage_fixtures import fixture, ContextStorageFixture
from context_budget_fixtures import profile
from actor_context_projection_fixtures import actor_projection_case
from claim_fixtures import UnitClaimAuthority
from construction_storage_fixtures import put
from task_execution_fixtures import UnitPhases
from test_actor_protocol import turn
from test_run_journal import command


class UnitBindingAuthority:
    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert binding.identity == public_task.identity and private_spec and baseline


class UnitExecutionAuthority:
    def __init__(self, phases: UnitPhases) -> None:
        self.phases = phases
        self.denied = False
        self.initial_denied = False

    def verify(
        self,
        plan: TaskExecutionPlan,
        source: ExecutionSourceFacts,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied:
            raise PermissionError("Synthetic execution physical right denied")
        assert (
            source.source.intent == plan.intent
            and reset == self.phases.closed.reset_plan
        )

    def verify_initial(
        self,
        plan: TaskExecutionPlan,
        source: ExecutionSourceFacts,
        facts: CandidateFacts,
        snapshot: RunSnapshot,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.initial_denied:
            raise PermissionError("Synthetic Actor physical right denied")
        assert facts.source == source.context and plan.intent == source.source.intent

    def verify_closed(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self.phases.verify_closed(plan, closed, operation, control)


@dataclass
class SingleSourceCase:
    data: ContextStorageFixture
    run: RunPlan
    binding: AttemptBinding
    skill_ref: EvidenceRef
    source: ExecutionTaskSource
    source_ref: EvidenceRef
    source_reader: OriginalExecutionTaskSource
    plans: EvidenceRunPlans
    claims: FileSourceClaims
    claim_authority: UnitClaimAuthority
    runs: FileRunJournal
    policy: EngineeringActorPolicy

    @property
    def inputs(self) -> EquivalenceInputs:
        return self.data.inputs


def source_case(root: Path) -> SingleSourceCase:
    root.mkdir()
    evidence = root / "evidence"
    evidence.mkdir()
    data = fixture(evidence, allowed_actions=("send_msg_to_user",))
    store, controls, inputs = data.store, data.adapter.controls, data.inputs
    data.publish(inputs.source, inputs.source.operation)
    source_ref = inputs.source_ref
    data.publish(data.comparison, data.comparison.operation)
    task = inputs.candidate_inputs.binding
    task_ref = inputs.candidate_inputs.prepared.task_binding_ref
    params = put(store, {"synthetic_parameters": True}, "model-parameters/1")
    model_ref = put(store, {"synthetic_model": True}, "model-binding/1")
    cfg = ActorContextConfiguration(
        policy=actor_projection_case().policy,
        profiles=(
            profile(
                provider="fixed-actor-worker",
                routing_ref=model_ref,
                configuration_ref=params,
                context_window=65536,
                output_reserve=4096,
                input_limit=61440,
                soft_target=24576,
            ),
        ),
    )
    selected = turn()
    policy = EngineeringActorPolicy(
        skill=selected.skill,
        memory=selected.memory,
        max_generations=1,
        max_interactions=1,
        actor_projection=FullAxProjection(),
        actor_context_ref=put(store, cfg, cfg.schema_version),
        candidate_id="explicit-engineering",
        revision_round=0,
    )
    policy_ref = put(store, policy, policy.schema_version)
    skill = put(store, policy.skill, "compact-skill/1", "public")
    execution_inputs = ExecutionTaskInputs(
        task_binding_ref=task_ref,
        source_context_receipt_ref=source_ref,
        skill_ref=skill,
        attempt_id=inputs.candidate.scope.attempt_id,
    )
    inputs_ref = put(store, execution_inputs, execution_inputs.schema_version)
    run = RunPlan(
        run_id="run",
        release_ref=put(store, {"unit_release": True}, "release-manifest/1"),
        purpose="engineering",
        split="train",
        split_manifest_ref=put(store, {"unit_split": "train"}),
        task_manifest_ref=put(store, {"unit_task": task.identity.task_id}),
        tasks=(task,),
        workload=ExecutionWorkload(
            execution_policy_ref=policy_ref, task_inputs_ref=inputs_ref, seed=0
        ),
        policies=RunPolicies(
            actor_memory=policy.memory,
            teacher_template=InactivePolicy(
                status="not_applicable", reason="Actor-only engineering task"
            ),
        ),
        models=(
            RoleModelPlan(
                role="actor",
                provider="fixed-actor-worker",
                model="unit-model",
                model_binding_ref=model_ref,
                parameters_ref=params,
                paid=False,
            ),
        ),
        resources=RunResources(
            configuration_ref=put(store, {"synthetic_resources": True}),
            max_parallel_tasks=1,
            max_actor_generations_per_attempt=1,
            max_interactions_per_attempt=1,
            operation_timeout_seconds=60,
            cleanup_timeout_seconds=30,
        ),
        run_capacity=JournalCapacity(
            max_attempts=1, max_entries=32, max_bytes=1024**2, max_entry_bytes=32768
        ),
        budget=None,
    )
    plans = EvidenceRunPlans(store, controls)
    bound = RunBinding(
        owner=inputs.candidate.scope.owner,
        plan_ref=plans.publish(run, command("single-plan")),
        release_ref=run.release_ref,
        submission_key="unit-single-source",
    )
    claimroot = root / "claims"
    claimroot.mkdir()
    claim_authority = UnitClaimAuthority()
    claims = FileSourceClaims(
        claimroot, "unit-single", controls, store, plans, claim_authority
    )
    claim = claims.claim(
        SourceClaimBinding(scope_id="unit-single", run=bound, task=task),
        command("single-claim"),
    )
    binding = AttemptBinding(
        run=bound,
        task=task.identity,
        attempt_id=execution_inputs.attempt_id,
        claim_ref=claim.reference,
    )
    reader = OriginalExecutionTaskSource(
        plans,
        claims,
        data.adapter,
        EvidenceTaskBindings(store, controls, UnitBindingAuthority()),
        store,
    )
    published = publish_execution_task_source(
        bound,
        claim.reference,
        command("single-source-publication"),
        reader=reader,
        evidence=store,
        controls=controls,
    )
    source = published.source
    runroot = root / "run"
    runroot.mkdir()
    runs = FileRunJournal(runroot, bound, controls, store, capacity=run.run_capacity)
    from test_run_journal import Harness

    Harness(
        runroot, store, runs, bound, claim.reference, data.switch, run.run_capacity
    ).running()
    return SingleSourceCase(
        data,
        run,
        binding,
        skill,
        source,
        published.source_ref,
        reader,
        plans,
        claims,
        claim_authority,
        runs,
        policy,
    )
