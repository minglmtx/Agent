"""Qualified unit source to normal claimed/default bindings; no resource effects.

Only the unit source graph/transport and an explicitly unacquired model premise
are supplied. Claims live in pytest's own directory. Nothing here is a runtime
permission supplier or a source of actual Actor/benchmark acceptance.
"""

from datetime import timedelta
import json
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
from lab_generate_skill.bootstrap.gitlab_group_execution_admission import (
    admit_gitlab_group_execution_source,
)
from lab_generate_skill.bootstrap.gitlab_group_owned_execution import (
    gitlab_group_owned_execution,
)
from lab_generate_skill.bootstrap.task_execution_bindings import (
    TaskExecutionDeclarations,
)
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_projection import FullAxProjection
from lab_generate_skill.domain.evaluation import EvaluationContract
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
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.run_plan import (
    RunPlan,
    RunResources,
    RoleModelPlan,
    ExecutionWorkload,
)
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.task_capture import TaskCapturePlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.trace_plan import TraceCapacity
from lab_generate_skill.evaluators.gitlab.group import REQUIREMENTS
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from actor_context_projection_fixtures import actor_projection_case
from context_budget_fixtures import profile
from construction_storage_fixtures import put
from test_actor_protocol import turn
from gitlab_group_source_fixtures import group_source_unit_case, retain


def owned_group_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, contracts: Any
) -> Any:
    x = group_source_unit_case(
        root, node, patch, contracts, "none", explicit_origin=True
    )
    c, source = x.site, x.qualified
    assert source is not None
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
    facts = x.facts.baseline_inputs
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
        candidate_id="unit-normal-group",
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
        submission_key="unit-group-candidate",
    )
    claims = root / "candidate-claims"
    claims.mkdir()
    admitted = admit_gitlab_group_execution_source(
        run,
        bound,
        source.material,
        x.owner.execution,
        x.owner.controller,
        read,
        claim_root=claims,
        claim_scope="unit-gitlab-group",
        evidence=store,
        controls=controls,
        source_reads=x.read_factory(store, read),
    )
    private = GroupSpec.model_validate_json(store.read(task.private_spec_ref))
    cfg = c.spec.configuration
    native = cfg.gitlab_group_inputs
    assert native is not None
    site_token = cfg.token.model_copy(
        update={
            "allocation_id": "candidate-site",
            "expected_resource_id": "candidate-site",
        }
    )
    cfg = cfg.model_copy(
        update={
            "token": site_token,
            "files": cfg.files.model_copy(
                update={
                    "instance_id": "candidate-site",
                    "node_root": str(node / "candidate"),
                }
            ),
            "gitlab_group_inputs": native.model_copy(update={"scope": scope}),
        }
    )
    site = c.spec.model_copy(update={"configuration": cfg})
    acquire = read.model_copy(
        update={
            "operation_id": "candidate-site-acquire",
            "allocation_id": site_token.allocation_id,
            "recovery_ref": site_token.recovery_ref,
        }
    )
    task_recovery = RecoveryPlan(
        recovery_id="candidate-task",
        owner=scope.owner,
        attempt_id=scope.attempt_id,
        baseline_ref=task.baseline_ref,
        restore_component_id="gitlab-group-creation",
        restore_component_version="1",
        state_coverage=facts.spec.task_reset_checks,
    )
    task_recovery_ref = put(store, task_recovery, task_recovery.schema_version)
    browser_recovery = task_recovery.model_copy(
        update={
            "recovery_id": "candidate-browser",
            "restore_component_id": "browser-close",
            "state_coverage": ("browser-processes",),
        }
    )
    browser = AllocationToken(
        allocation_id="candidate-browser",
        owner=scope.owner,
        scope="attempt",
        attempt_id=scope.attempt_id,
        resource_kind="browser",
        expected_resource_id="candidate-browser",
        provider_id="fixed-browser-worker",
        provider_version="3",
        recovery_ref=put(store, browser_recovery, browser_recovery.schema_version),
    )
    execute = read.model_copy(
        update={"operation_id": "candidate-task", "attempt_id": scope.attempt_id}
    )
    snapshot = execute.model_copy(
        update={
            "operation_id": "candidate-snapshot",
            "allocation_id": site_token.allocation_id,
            "recovery_ref": task_recovery_ref,
        }
    )
    prepare = snapshot.model_copy(update={"operation_id": "candidate-prepare"})
    environment = snapshot.model_copy(
        update={
            "operation_id": "candidate-environment",
            "recovery_ref": site_token.recovery_ref,
        }
    )
    resource_read = acquire.model_copy(
        update={
            "operation_id": "candidate-resource-read",
            "mode": "cleanup",
            "parent_operation_id": acquire.operation_id,
        }
    )
    declaration = SiteTaskPreparationPlan(
        scope=scope,
        site_spec_ref=put(store, site, site.schema_version),
        task_binding_ref=task_ref,
        private_input_ref=put(store, private, private.schema_version),
        snapshot_schema="gitlab-group-recovery/1",
        snapshot_operation=snapshot,
        prepare_operation=prepare,
        environment_operation=environment,
        resource_read_operation=resource_read,
    )
    reset = ResetPlan(
        scope=scope,
        parent_operation_id=prepare.operation_id,
        spec_ref=task.baseline_ref,
        task_recovery_ref=task_recovery_ref,
        environment_recovery_ref=site_token.recovery_ref,
        attempt_allocations=(browser,),
    )
    capture = TaskCapturePlan(
        scope=scope,
        requirements=REQUIREMENTS,
        page_operation_id="candidate-page",
        close_operation_id="candidate-capture-close",
        guard_operation_id="candidate-guard",
        page_collector_id="gitlab-page-health",
        page_collector_version="1",
        guard_collector_id="gitlab-group-creation",
        guard_collector_version="1",
        close_seconds=60,
    )
    final = TaskFinalizationPlan(
        scope=scope,
        browser_close_operation_id="candidate-browser-close",
        restore_operation_id="candidate-restore",
        resume_operation_id="candidate-resume",
        qualification_operation_id="candidate-reset-facts",
        reset_operation_id="candidate-safe-reset",
    )
    plan = TaskExecutionPlan(
        schema_version="task-execution-plan/2",
        intent=admitted.published.source.intent,
        source_ref=admitted.published.source_ref,
        reset_plan_ref=put(store, reset, reset.schema_version),
        declaration_ref=put(store, declaration, declaration.schema_version),
        skill_ref=skill_ref,
        evaluation=EvaluationContract(
            identity=task.identity,
            attempt_id=scope.attempt_id,
            task_contract_ref=task_ref,
            public_task_ref=task.public_task_ref,
            completion_spec_ref=task.private_spec_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        ),
        operation=execute,
        read_operation=read,
        cleanup_seconds=60,
    )
    d = TaskExecutionDeclarations(
        plan,
        declaration,
        reset,
        capture,
        put(store, capture, capture.schema_version),
        final,
        put(store, final, final.schema_version),
    )
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

    owned = gitlab_group_owned_execution(
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
    return SimpleNamespace(source=x, owned=owned, admitted=admitted, declarations=d)
