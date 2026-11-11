"""Explicit synthetic historical source, frozen before candidate preparation.

All links are real immutable CAS bytes. Historical service/closure/permission
facts are unit premises, never actual source qualification or replay.
"""

from lab_generate_skill.domain.baseline import (
    BaselineInputs,
    InitialStateChecks,
    assemble_baseline,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.lifecycle import (
    ClosureReceipt,
    RecoveryPlan,
    OperationContext,
)
from typing import Any
from retrieval_fixtures import reference
from lab_generate_skill.domain.preparation import (
    EnvironmentBaseline,
    PreparationReceipt,
    PreparedTask,
)
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
    assemble_public_context,
)
from lab_generate_skill.domain.reset import (
    ResetPlan,
    ResetInputs,
    TaskResetReceipt,
    EnvironmentResetReceipt,
    ResetHealthReceipt,
    assemble_reset,
)
from lab_generate_skill.domain.state_checks import StateChecks
from map_task_preparation_port_fixtures import MapPreparationPortCase
from observation_fixtures import sample_observation
from preparation_record_fixtures import put


def historical_source(
    p: MapPreparationPortCase,
) -> tuple[PublicContextInputs, PublicContextReceipt, EvidenceRef]:
    c, n = p.original, p.source.native
    store = c.resource.evidence
    scope = c.scope.model_copy(
        update={
            "attempt_id": "unit-historical-source",
            "context_id": "unit-source-context",
        }
    )

    assert c.worker is not None and c.worker.tasks is not None
    assert c.worker.tasks.guard.initial is not None

    def op(name: str, **changes: Any) -> OperationContext:
        return p.plan.operation.model_copy(
            update={
                "operation_id": "unit-source-" + name,
                "attempt_id": scope.attempt_id,
                **changes,
            }
        )

    def checked(names: tuple[str, ...]) -> StateChecks:
        return StateChecks(
            required=names,
            checks=tuple(
                CheckResult(
                    name=name,
                    status="pass",
                    reason_code="EXPLICIT_SYNTHETIC_HISTORICAL_FACT",
                    evidence=(reference({"unit_only": name}, store=store),),
                )
                for name in names
            ),
        )

    task_recovery = RecoveryPlan(
        recovery_id="unit-source-task",
        owner=scope.owner,
        attempt_id=scope.attempt_id,
        baseline_ref=n.spec_ref,
        restore_component_id="unit-source-restore",
        restore_component_version="1",
        state_coverage=n.spec.task_reset_checks,
    )
    task_recovery_ref = put(store, task_recovery)
    environment = EnvironmentBaseline(
        scope=scope,
        operation=op("environment", allocation_id=c.resource.spec.token.allocation_id),
        allocation=c.resource.spec.token,
        spec_ref=n.spec_ref,
        checks=checked(n.spec.environment_checks),
        measured_state_sha256=c.worker.tasks.guard.initial.sha256,
    )
    environment_ref = put(store, environment)
    preparation = PreparationReceipt(
        scope=scope,
        operation=op("prepare", recovery_ref=task_recovery_ref),
        task_binding_ref=n.binding_ref,
        spec_ref=n.spec_ref,
        environment_ref=environment_ref,
        recovery_ref=task_recovery_ref,
        checks=checked(n.spec.preparation_checks),
    )
    preparation_ref = put(store, preparation)
    prepared = PreparedTask(
        scope=scope,
        public_task=n.public,
        task_binding_ref=n.binding_ref,
        spec_ref=n.spec_ref,
        preparation_ref=preparation_ref,
        private_checks_ref=n.binding.private_spec_ref,
        recovery_ref=task_recovery_ref,
    )
    prepared_ref = put(store, prepared)
    observation = sample_observation(
        scope.task, context_id=scope.context_id, attempt_id=scope.attempt_id
    )
    observation = observation.model_copy(
        update={
            "tabs": tuple(
                t.model_copy(update={"url": n.public.start_url})
                for t in observation.tabs
            )
        }
    )
    observation_ref = put(store, observation, "public")
    initial = InitialStateChecks(
        scope=scope,
        operation=op("initial"),
        spec_ref=n.spec_ref,
        prepared_ref=prepared_ref,
        observation_ref=observation_ref,
        checks=checked(n.spec.initial_checks),
        measured_state_sha256="2" * 64,
    )
    baseline_inputs = BaselineInputs(
        binding=n.binding,
        public_task=n.public,
        spec=n.spec,
        spec_ref=n.spec_ref,
        environment=environment,
        environment_ref=environment_ref,
        preparation=preparation,
        preparation_ref=preparation_ref,
        prepared=prepared,
        prepared_ref=prepared_ref,
        observation=observation,
        observation_ref=observation_ref,
        initial=initial,
        initial_ref=put(store, initial),
    )
    baseline = assemble_baseline(baseline_inputs, op("baseline"))
    baseline_ref = put(store, baseline)
    browser_recovery = RecoveryPlan(
        recovery_id="unit-source-browser",
        owner=scope.owner,
        attempt_id=scope.attempt_id,
        baseline_ref=n.spec_ref,
        restore_component_id="unit-source-close",
        restore_component_version="1",
        state_coverage=("browser-processes",),
    )
    token = p.reset.attempt_allocations[0].model_copy(
        update={
            "allocation_id": "unit-source-browser",
            "expected_resource_id": "unit-source-instance",
            "attempt_id": scope.attempt_id,
            "recovery_ref": put(store, browser_recovery),
        }
    )
    reset_plan = ResetPlan(
        scope=scope,
        parent_operation_id=preparation.operation.operation_id,
        spec_ref=n.spec_ref,
        task_recovery_ref=task_recovery_ref,
        environment_recovery_ref=environment.allocation.recovery_ref,
        attempt_allocations=(token,),
    )
    closure = ClosureReceipt(
        token=token,
        operation_id="unit-source-close",
        status="closed",
        evidence=(reference({"synthetic_historical_closure": True}, store=store),),
    )
    closure_ref = put(store, closure)

    def clean(name: str, **changes: Any) -> OperationContext:
        return op(
            name,
            mode="cleanup",
            parent_operation_id=reset_plan.parent_operation_id,
            **changes,
        )

    task_reset = TaskResetReceipt(
        scope=scope,
        operation=clean("task-reset", recovery_ref=task_recovery_ref),
        recovery_ref=task_recovery_ref,
        after_closure_refs=(closure_ref,),
        checks=checked(n.spec.task_reset_checks),
    )
    task_reset_ref = put(store, task_reset)
    env_reset = EnvironmentResetReceipt(
        scope=scope,
        operation=clean(
            "environment-reset", recovery_ref=reset_plan.environment_recovery_ref
        ),
        recovery_ref=reset_plan.environment_recovery_ref,
        after_task_reset_ref=task_reset_ref,
        checks=checked(n.spec.environment_reset_checks),
    )
    env_reset_ref = put(store, env_reset)
    health = ResetHealthReceipt(
        scope=scope,
        operation=clean("health"),
        after_environment_reset_ref=env_reset_ref,
        checks=checked(n.spec.health_checks),
    )
    environment_recovery = RecoveryPlan.model_validate_json(
        store.read(reset_plan.environment_recovery_ref)
    )
    reset_inputs = ResetInputs(
        plan=reset_plan,
        plan_ref=put(store, reset_plan),
        spec=n.spec,
        task_recovery=task_recovery,
        environment_recovery=environment_recovery,
        closures=(closure,),
        closure_refs=(closure_ref,),
        task=task_reset,
        task_ref=task_reset_ref,
        environment=env_reset,
        environment_ref=env_reset_ref,
        health=health,
        health_ref=put(store, health),
    )
    reset = assemble_reset(reset_inputs, clean("reset"))
    context = PublicConstructionContext(
        context_id=scope.context_id,
        task=n.public,
        initial_observation_ref=observation_ref,
    )
    context_ref = put(store, context, "public")
    inputs = PublicContextInputs(
        context=context,
        context_ref=context_ref,
        baseline_inputs=baseline_inputs,
        baseline=baseline,
        baseline_ref=baseline_ref,
        reset_inputs=reset_inputs,
        reset=reset,
        reset_ref=put(store, reset),
    )
    receipt = assemble_public_context(inputs, op("freeze", attempt_id=None))
    return inputs, receipt, put(store, receipt)
