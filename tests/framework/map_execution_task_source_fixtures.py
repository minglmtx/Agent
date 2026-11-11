"""Actor-only Map inputs/claim/source with explicit synthetic resource rights.

No construction, retrieval, Generator or Teacher records are created. The
independent source is a unit premise, not an actual source qualification.
"""

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.bootstrap.actor_context_runtime import freeze_actor_context
from lab_generate_skill.bootstrap.execution_task_source import (
    publish_execution_task_source,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.optional_policies import RunPolicies, InactivePolicy
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.run_plan import (
    RunPlan,
    RunResources,
    RoleModelPlan,
    ExecutionWorkload,
)
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.evaluators.map.navigation import REQUIREMENTS
from claim_fixtures import UnitClaimAuthority
from map_task_frozen_source_fixtures import FrozenSource
from map_task_preparation_port_fixtures import MapPreparationPortCase
from construction_storage_fixtures import put
from preparation_record_fixtures import put as record
from task_initialization_port_fixtures import UnitNavigationContextAuthority
from test_run_journal import Harness, CancelSwitch


@dataclass
class SingleMapJournals:
    runs: FileRunJournal
    claims: FileSourceClaims
    plans: EvidenceRunPlans
    context: UnitNavigationContextAuthority
    source: PublicContextReceipt
    source_ref: EvidenceRef
    source_reader: OriginalExecutionTaskSource
    claim_authority: UnitClaimAuthority


def single_map_journals(
    p: MapPreparationPortCase,
    native: SimpleNamespace,
    root: Path,
    frozen: FrozenSource,
) -> SingleMapJournals:
    assert p.requests == [] and p.preparation.state.phase == "new"
    root.mkdir()
    store, controls = p.original.resource.evidence, p.original.resource.controls
    _, source, context_ref = frozen
    assert source.scope.owner == p.original.scope.owner
    assert source.scope.attempt_id != p.original.scope.attempt_id

    def op(name: str) -> OperationContext:
        return p.plan.read_operation.model_copy(
            update={"operation_id": "single-map-" + name}
        )

    def copy_ref(ref: EvidenceRef) -> None:
        raw = native.actor.evidence.read(ref)
        metadata = EvidenceMetadata.model_validate(
            ref.model_dump(
                include={"media_type", "content_schema", "visibility", "producer"}
            )
        )
        assert store.put(raw, metadata) == ref

    for ref in (
        native.scope.binding.release_ref,
        native.scope.binding.model_binding_ref,
        native.scope.binding.spec_ref,
        native.scope.binding.acquired_ref,
        native.scope.binding.resource.recovery_ref,
        native.policy.software_evidence_ref,
    ):
        copy_ref(ref)
    model = ActorModelBinding.model_validate_json(
        store.read(native.scope.binding.model_binding_ref)
    )
    copy_ref(model.engine_config_ref)
    parameters_ref = put(store, native.params, "model-parameters/1")
    cfg = freeze_actor_context(
        native.scope.spec,
        (parameters_ref,),
        native.policy,
        store,
        soft_target=24576,
        control=controls.bind(op("freeze-context")),
    )
    memory = InactivePolicy(
        status="not_applicable", reason="No enabled cross-page memory"
    )
    skill = CompactSkill.model_validate_json(store.read(p.plan.skill_ref))
    policy = EngineeringActorPolicy(
        skill=skill,
        memory=memory,
        max_generations=1,
        max_interactions=1,
        actor_projection=FullAxProjection(),
        actor_context_ref=record(store, cfg),
        candidate_id="original-candidate-0",
        revision_round=0,
    )
    inputs = ExecutionTaskInputs(
        task_binding_ref=p.source.native.binding_ref,
        source_context_receipt_ref=context_ref,
        skill_ref=p.plan.skill_ref,
        attempt_id=p.original.scope.attempt_id,
    )
    run = RunPlan(
        run_id=p.original.scope.owner.run_id,
        release_ref=native.scope.binding.release_ref,
        purpose="engineering",
        split="train",
        split_manifest_ref=put(store, {"synthetic_split": "train"}),
        task_manifest_ref=put(store, {"synthetic_task": p.original.scope.task.task_id}),
        tasks=(p.source.native.binding,),
        workload=ExecutionWorkload(
            execution_policy_ref=record(store, policy),
            task_inputs_ref=record(store, inputs),
            seed=0,
        ),
        policies=RunPolicies(
            actor_memory=memory,
            teacher_template=InactivePolicy(
                status="not_applicable", reason="Actor-only Map execution"
            ),
        ),
        models=(
            RoleModelPlan(
                role="actor",
                provider="fixed-actor-worker",
                model=model.model,
                model_binding_ref=native.scope.binding.model_binding_ref,
                parameters_ref=parameters_ref,
                paid=False,
            ),
        ),
        resources=RunResources(
            configuration_ref=put(store, {"synthetic_resources": True}),
            max_parallel_tasks=1,
            max_actor_generations_per_attempt=1,
            max_interactions_per_attempt=1,
            operation_timeout_seconds=120,
            cleanup_timeout_seconds=30,
        ),
        run_capacity=JournalCapacity(
            max_attempts=1, max_entries=32, max_bytes=4 * 1024**2, max_entry_bytes=65536
        ),
        budget=None,
    )
    plans = EvidenceRunPlans(store, controls)
    bound = RunBinding(
        owner=p.original.scope.owner,
        plan_ref=plans.publish(run, op("plan")),
        release_ref=run.release_ref,
        submission_key="unit-single-map-" + p.original.scope.task.source_task_id,
    )
    (root / "claims").mkdir()
    claim_authority = UnitClaimAuthority()
    claims = FileSourceClaims(
        root / "claims", "unit-single-map", controls, store, plans, claim_authority
    )
    claim = claims.claim(
        SourceClaimBinding(
            scope_id="unit-single-map", run=bound, task=p.source.native.binding
        ),
        op("claim"),
    )
    context = UnitNavigationContextAuthority()
    reader = OriginalExecutionTaskSource(
        plans,
        claims,
        EvidenceContextRecords(store, controls, context),
        p.source.native.bindings,
        store,
    )
    published = publish_execution_task_source(
        bound,
        claim.reference,
        op("publish-source"),
        reader=reader,
        evidence=store,
        controls=controls,
    )
    p.plan = TaskExecutionPlan.model_validate(
        {
            **p.plan.model_dump(),
            "schema_version": "task-execution-plan/2",
            "intent": published.source.intent,
            "source_ref": published.source_ref,
            "evaluation": p.plan.evaluation.model_copy(
                update={"requirements": REQUIREMENTS}
            ),
        }
    )
    (root / "run").mkdir()
    runs = FileRunJournal(
        root / "run", bound, controls, store, capacity=run.run_capacity
    )
    Harness(
        root / "run",
        store,
        runs,
        bound,
        claim.reference,
        CancelSwitch(),
        run.run_capacity,
    ).running()
    return SingleMapJournals(
        runs, claims, plans, context, source, context_ref, reader, claim_authority
    )
