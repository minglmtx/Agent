"""Current complete run/construction/claim CAS; historical/source rights synthetic.

All declarations precede candidate task effects. Generator records below are
explicit fixture bytes, never actual model/API requests or training targets.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.adapters.ledger.construction_journal import (
    FileConstructionJournal,
)
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.construction import AttemptPlanned, ConstructionPlan
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.run_plan import RunPlan, ConstructionWorkload
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.evaluators.map.navigation import REQUIREMENTS
from claim_fixtures import UnitClaimAuthority
from construction_storage_fixtures import StorageFixture, UnitConstructionAuthority, put
from map_task_preparation_port_fixtures import MapPreparationPortCase
from retrieval_fixtures import fixture as retrieval_fixture
from task_initialization_source_fixtures import historical_source
from lab_generate_skill.domain.public_context import PublicContextInputs
from task_initialization_port_fixtures import UnitNavigationContextAuthority
from test_evidence_run_plans import persisted_plan
from test_retrieval_evidence import UnitAuthority as UnitRetrievalAuthority
from test_run_journal import Harness, CancelSwitch
from map_construction_task_evidence_fixtures import UnitCurrentTaskConstructionAuthority


@dataclass
class CurrentMapJournals:
    data: StorageFixture
    construction: FileConstructionJournal
    runs: FileRunJournal
    claims: FileSourceClaims
    plans: EvidenceRunPlans
    context: UnitNavigationContextAuthority
    source: PublicContextReceipt
    source_ref: EvidenceRef


def current_map_journals(
    p: MapPreparationPortCase,
    native: Any,
    root: Path,
    *,
    frozen_source: (
        tuple[PublicContextInputs, PublicContextReceipt, EvidenceRef] | None
    ) = None,
    register_attempt: bool = True,
    current_task_results: bool = False,
) -> CurrentMapJournals:
    assert p.requests == [] and p.preparation.state.phase == "new"
    assert p.original.scope.owner == native.scope.binding.resource.owner
    store, controls = p.original.resource.evidence, p.original.resource.controls
    inputs, source, source_ref = (
        historical_source(p) if frozen_source is None else frozen_source
    )
    root.mkdir()
    (root / "journal").mkdir()
    (root / "claims").mkdir()
    (root / "run").mkdir()

    def op(name: str) -> OperationContext:
        return p.plan.read_operation.model_copy(
            update={"operation_id": "current-map-" + name}
        )

    seen: set[str] = set()

    def copy_ref(reference: EvidenceRef) -> None:
        if reference.sha256 in seen:
            return
        seen.add(reference.sha256)
        raw = native.actor.evidence.read(reference)
        metadata = EvidenceMetadata.model_validate(
            reference.model_dump(
                include={"media_type", "content_schema", "visibility", "producer"}
            )
        )
        assert store.put(raw, metadata) == reference

    for ref in [
        native.scope.binding.release_ref,
        native.scope.binding.model_binding_ref,
        native.scope.binding.spec_ref,
        native.scope.binding.acquired_ref,
        native.scope.binding.resource.recovery_ref,
        native.policy.software_evidence_ref,
    ]:
        copy_ref(ref)
    model = ActorModelBinding.model_validate_json(
        store.read(native.scope.binding.model_binding_ref)
    )
    copy_ref(model.engine_config_ref)
    params = put(store, native.params, "model-parameters/1")
    retrieved = retrieval_fixture(
        store, public_context=inputs.context, public_context_ref=inputs.context_ref
    )
    run = persisted_plan(store)
    assert isinstance(run.workload, ConstructionWorkload)
    run = RunPlan.model_validate(
        run.model_copy(
            update={
                "release_ref": native.scope.binding.release_ref,
                "tasks": (p.source.native.binding,),
                "split_manifest_ref": retrieved.scope.split_ref,
                "workload": run.workload.model_copy(
                    update={"bank_ref": retrieved.scope.bank_ref}
                ),
                "resources": run.resources.model_copy(
                    update={
                        "max_actor_generations_per_attempt": 1,
                        "max_interactions_per_attempt": 1,
                    }
                ),
                "models": tuple(
                    (
                        role.model_copy(
                            update={
                                "provider": "fixed-actor-worker",
                                "model": model.model,
                                "model_binding_ref": native.scope.binding.model_binding_ref,
                                "parameters_ref": params,
                                "paid": False,
                            }
                        )
                        if role.role == "actor"
                        else role
                    )
                    for role in run.models
                ),
            }
        )
    )
    plans = EvidenceRunPlans(store, controls)
    run_ref = plans.publish(run, op("publish-plan"))
    bound = RunBinding(
        owner=p.original.scope.owner,
        plan_ref=run_ref,
        release_ref=run.release_ref,
        submission_key="unit-current-map-" + p.original.scope.task.source_task_id,
    )
    claim_authority, context = UnitClaimAuthority(), UnitNavigationContextAuthority()
    claims = FileSourceClaims(
        root / "claims", "unit-scope", controls, store, plans, claim_authority
    )
    claim = claims.claim(
        SourceClaimBinding(
            scope_id="unit-scope", run=bound, task=p.source.native.binding
        ),
        op("claim"),
    )
    retrieval_authority = UnitRetrievalAuthority(store)
    retrieval = EvidenceRetrievalRecords(store, controls, retrieval_authority).publish(
        retrieved.result, op("retrieval")
    )
    construction_plan = ConstructionPlan.from_run_plan(
        run,
        bound,
        p.original.scope.task.task_id,
        claim_ref=claim.reference,
        public_context_ref=inputs.context_ref,
        context_receipt_ref=source_ref,
        retrieval_ref=retrieval,
        retrieval_scope=retrieved.scope,
    )
    data = StorageFixture(
        root,
        store,
        construction_plan,
        (
            UnitCurrentTaskConstructionAuthority(store)
            if current_task_results
            else UnitConstructionAuthority(store)
        ),
        context,
        retrieval_authority,
        claim_authority,
    )
    construction = data.journal()
    progress = construction.create(construction_plan, op("create-construction"))
    event = data.event(progress)
    while not isinstance(event, AttemptPlanned):
        progress = construction.append(event, progress.revision, event.operation)
        event = data.event(progress)
    intent = event.intent.model_copy(
        update={
            "binding": event.intent.binding.model_copy(
                update={"attempt_id": p.original.scope.attempt_id}
            )
        }
    )
    event = event.model_copy(update={"intent": intent})
    if register_attempt:
        progress = construction.append(event, progress.revision, event.operation)
        assert progress.project().pending_attempt == intent
    else:
        assert progress.project().pending_attempt is None
        assert progress.project().next_action.kind == "execute"
    candidate = progress.project().candidates[intent.candidate_slot].response.skill
    skill_ref = put(store, candidate, "compact-skill/1", "public")
    p.plan = TaskExecutionPlan.model_validate(
        p.plan.model_copy(
            update={
                "intent": intent,
                "skill_ref": skill_ref,
                "evaluation": p.plan.evaluation.model_copy(
                    update={"requirements": REQUIREMENTS}
                ),
            }
        )
    )
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
    return CurrentMapJournals(
        data, construction, runs, claims, plans, context, source, source_ref
    )
