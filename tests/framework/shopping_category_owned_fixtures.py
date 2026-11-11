"""Qualified unit source to normal claimed/default bindings; no resource effects.

Only the unit source graph/transport and an explicitly unacquired model premise
are supplied. Claims live in pytest's own directory. Nothing here is a runtime
permission supplier or a source of actual Actor/benchmark acceptance.
"""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest

from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.application.execution_task_phase_source import (
    ExecutionTaskPhaseSources,
)
from lab_generate_skill.bootstrap.shopping_category_execution_admission import (
    admit_shopping_category_execution_source,
)
from lab_generate_skill.bootstrap.shopping_category_owned_execution import (
    shopping_category_owned_execution,
)
from lab_generate_skill.bootstrap.shopping_category_site_configuration import (
    shopping_category_site_configuration,
)
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
)
from lab_generate_skill.domain.local_actor import LocalActorBinding
from lab_generate_skill.domain.optional_policies import InactivePolicy, RunPolicies
from lab_generate_skill.domain.run_plan import (
    RunPlan,
    RunResources,
    RoleModelPlan,
    ExecutionWorkload,
)
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.trace_plan import TraceCapacity
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from actor_context_projection_fixtures import actor_projection_case
from context_budget_fixtures import profile
from construction_storage_fixtures import put
from test_actor_protocol import turn
from shopping_category_source_fixtures import source_unit_case
from shopping_category_owned_reads import CategoryUnitRead
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.domain.baseline import BaselineReceipt


def owned_navigation_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, original: Any
) -> Any:
    x = source_unit_case(root, node, patch, original, "none")
    c, source = x.site, x.run()
    x.qualified = source
    store, controls, clock = c.evidence, c.controls, c.clock
    scope = x.owner.scope.model_copy(
        update={"attempt_id": "candidate", "context_id": "candidate"}
    )
    read = OperationContext(
        operation_id="candidate-admission",
        run_id=scope.owner.run_id,
        owner_id=scope.owner.owner_id,
        deadline=clock.utcnow() + timedelta(seconds=180),
    )
    baseline = StateReads(store).parse(
        source.receipt.baseline_ref,
        "baseline-receipt/1",
        BaselineReceipt,
        controls.bind(read),
    )
    facts = BaselineEvidenceReader(store).verify(baseline, controls.bind(read))
    task = facts.binding
    task_ref = facts.prepared.task_binding_ref
    selected = turn()
    memory = InactivePolicy(
        status="not_applicable", reason="Unit normal composition, no memory"
    )
    params = put(store, {"declaration_only": True}, "model-parameters/1")
    model_ref = put(store, {"declaration_only": True}, "model-binding/1")
    context = ActorContextConfiguration(
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
    policy = EngineeringActorPolicy(
        skill=selected.skill,
        memory=memory,
        max_generations=1,
        max_interactions=1,
        actor_projection=FullAxProjection(),
        actor_context_ref=put(store, context, context.schema_version),
        candidate_id="unit-normal-category",
        revision_round=0,
    )
    skill_ref = put(store, selected.skill, "compact-skill/1", "public")
    inputs = ExecutionTaskInputs(
        task_binding_ref=task_ref,
        source_context_receipt_ref=source.material.context_ref,
        skill_ref=skill_ref,
        attempt_id=scope.attempt_id,
    )
    release = c.spec.configuration.installation.manifest_ref
    retain(
        store,
        c.spec.configuration.installation.manifest.model_dump_json().encode(),
        release,
    )
    run = RunPlan(
        run_id=scope.owner.run_id,
        release_ref=release,
        purpose="engineering",
        split="train",
        split_manifest_ref=put(store, {"unit_split": "train"}),
        task_manifest_ref=put(store, {"unit_task": task.identity.task_id}),
        tasks=(task,),
        workload=ExecutionWorkload(
            execution_policy_ref=put(store, policy, policy.schema_version),
            task_inputs_ref=put(store, inputs, inputs.schema_version),
            seed=0,
        ),
        policies=RunPolicies(
            actor_memory=memory,
            teacher_template=InactivePolicy(
                status="not_applicable", reason="Unit Actor-only binding"
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
            configuration_ref=put(store, {"declaration_only": True}),
            max_parallel_tasks=1,
            max_actor_generations_per_attempt=1,
            max_interactions_per_attempt=1,
            operation_timeout_seconds=180,
            cleanup_timeout_seconds=60,
        ),
        run_capacity=JournalCapacity(
            max_attempts=1,
            max_entries=128,
            max_bytes=8 * 1024**2,
            max_entry_bytes=65536,
        ),
        budget=None,
    )
    meta = EvidenceMetadata(
        media_type="application/json",
        content_schema=run.schema_version,
        visibility="private",
        producer="run-plans-v1",
    )
    bound = RunBinding(
        owner=scope.owner,
        plan_ref=evidence_reference(run.model_dump_json().encode(), meta),
        release_ref=release,
        submission_key="unit-category-candidate",
    )
    claims = root / "candidate-claims"
    claims.mkdir()
    admitted = admit_shopping_category_execution_source(
        run,
        bound,
        source.material,
        x.owner.execution,
        x.owner.controller,
        read,
        claim_root=claims,
        claim_scope="unit-shopping-category-navigation",
        evidence=store,
        controls=controls,
        source_reads=CategoryUnitRead(x, root / "evidence", read),
    )
    private = CategoryNavigationExecutionInput(
        spec=json_to_private(store.read(task.private_spec_ref))
    )
    cfg = c.spec.configuration
    native = cfg.shopping_category_inputs
    assert native is not None
    site_token = cfg.token.model_copy(
        update={
            "allocation_id": "candidate-site",
            "expected_resource_id": "candidate-site",
        }
    )
    cfg = shopping_category_site_configuration(
        private.spec,
        scope,
        site_token,
        cfg.files.model_copy(
            update={
                "instance_id": "candidate-site",
                "node_root": str(node / "candidate"),
            }
        ),
        cfg.installation,
        native.origin,
    )
    site = c.spec.model_copy(update={"configuration": cfg})
    acquire = read.model_copy(
        update={
            "operation_id": "candidate-site-acquire",
            "allocation_id": site_token.allocation_id,
            "recovery_ref": site_token.recovery_ref,
        }
    )
    from lab_generate_skill.bootstrap.shopping_category_execution_configuration import (
        prepare_category_execution_configuration,
    )

    environment = RecoveryPlan.model_validate_json(
        store.read(site.token.recovery_ref, controls.bind(read))
    )
    configuration_arguments = dict(
        source=source,
        admission=admitted,
        inputs=inputs,
        private=private.spec,
        scope=scope,
        site=site,
        acquisition=acquire,
        environment=environment,
        operation=read,
        read_operation=read,
        evidence=store,
        controls=controls,
        prefix="candidate",
        metadata_cleanup_seconds=60,
        physical_close_seconds=60,
    )
    d = prepare_category_execution_configuration(**configuration_arguments)
    plan = d.plan
    task_recovery_ref = d.reset.task_recovery_ref
    run_root = root / "candidate-run"
    run_root.mkdir()
    runs = FileRunJournal(run_root, bound, controls, store, capacity=run.run_capacity)
    from test_run_journal import Harness, CancelSwitch

    Harness(
        run_root,
        store,
        runs,
        bound,
        admitted.claim.reference,
        CancelSwitch(),
        run.run_capacity,
    ).running()
    owner = ClaimedRunResourceOwner(
        admitted.authority,
        admitted.claim.reference,
        read,
        claims=admitted.claims,
        runs=runs,
        plans=admitted.plans,
        evidence=store,
        task_plan=plan,
        sources=ExecutionTaskPhaseSources(admitted.reader),
    )
    model_token = AllocationToken(
        allocation_id="unit-model",
        owner=scope.owner,
        scope="batch",
        resource_kind="actor",
        expected_resource_id="unit-model",
        provider_id="fixed-actor-worker",
        provider_version="1",
        recovery_ref=task_recovery_ref,
    )

    class UnacquiredUnitModel(ActorExecutionScope):
        def __init__(self) -> None:
            self.binding = LocalActorBinding(
                resource=model_token,
                release_ref=release,
                model_binding_ref=model_ref,
                spec_ref=put(store, {"unit": True}, "actor-resource-spec/1"),
                acquired_ref=put(store, {"unit": True}, "actor-resource-fact/1"),
                cleanup_seconds=60,
            )

    def no_browser(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Pure composition cannot construct/acquire a browser")

    owned = shopping_category_owned_execution(
        d,
        owner,
        admitted.reader,
        UnacquiredUnitModel(),
        site,
        acquire,
        no_browser,
        journal=c.journal,
        bindings=admitted.bindings,
        controls=controls,
        clock=clock,
        trace_root=root / "candidate-trace",
        calls_root=root / "candidate-calls",
        trace_capacity=TraceCapacity(
            max_events=128,
            max_bytes=4 * 1024**2,
            max_event_bytes=65536,
            max_trace_bytes=4 * 1024**2,
        ),
    )
    return SimpleNamespace(
        source=x,
        owned=owned,
        admitted=admitted,
        declarations=d,
        configuration_arguments=configuration_arguments,
    )


def json_to_private(raw: bytes) -> Any:
    from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
        CategoryNavigationSpec,
    )

    return CategoryNavigationSpec.model_validate_json(raw)


def retain(store: Any, raw: bytes, reference: Any) -> None:
    metadata = EvidenceMetadata.model_validate(
        reference.model_dump(
            include={"media_type", "content_schema", "visibility", "producer"}
        )
    )
    assert store.put(raw, metadata) == reference
