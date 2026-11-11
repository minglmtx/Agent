"""Explicit synthetic state facts; no real provider/claim qualification."""

from lab_generate_skill.domain.baseline import BaselineInputs, InitialStateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    ClosureReceipt,
    OperationContext,
    RecoveryPlan,
    ResourceOwner,
)
from lab_generate_skill.domain.preparation import (
    EnvironmentBaseline,
    PreparationReceipt,
    PreparedTask,
)
from lab_generate_skill.domain.reset import (
    ResetPlan,
    ResetInputs,
    TaskResetReceipt,
    EnvironmentResetReceipt,
    ResetHealthReceipt,
)
from lab_generate_skill.domain.state_checks import InitialStateSpec, StateChecks
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from observation_fixtures import sample_observation
from retrieval_fixtures import reference
from test_core_contracts import identity
from test_run_journal import command


def scope() -> StateScope:
    return StateScope(
        owner=ResourceOwner(
            run_id="run", owner_id="owner", job_id="job", worker_id="worker"
        ),
        task=identity(),
        attempt_id="attempt",
        context_id="context",
    )


def op(
    name: str,
    *,
    cleanup: bool = False,
    recovery: EvidenceRef | None = None,
    allocation: str | None = None,
) -> OperationContext:
    return command(
        name,
        attempt="attempt",
        cleanup_parent="original-execution" if cleanup else None,
    ).model_copy(update={"recovery_ref": recovery, "allocation_id": allocation})


def specification() -> InitialStateSpec:
    return InitialStateSpec(
        spec_id="initial",
        task=identity(),
        environment_checks=("environment",),
        preparation_checks=("prepared",),
        initial_checks=("initial",),
        equivalence_checks=("public_state",),
        task_reset_checks=("database", "mail"),
        environment_reset_checks=("service",),
        health_checks=("health", "protected"),
    )


def checks(required: tuple[str, ...]) -> StateChecks:
    return StateChecks(
        required=required,
        checks=tuple(
            CheckResult(
                name=name,
                status="pass",
                reason_code="UNIT_CHECK",
                evidence=(reference({"state": name}),),
            )
            for name in required
        ),
    )


def recovery(attempt: bool) -> RecoveryPlan:
    spec = specification()
    return RecoveryPlan(
        recovery_id="task" if attempt else "environment",
        owner=scope().owner,
        attempt_id="attempt" if attempt else None,
        baseline_ref=reference({"baseline": "unit"}),
        restore_component_id="unit-restore",
        restore_component_version="1",
        state_coverage=(
            spec.task_reset_checks if attempt else spec.environment_reset_checks
        ),
    )


def allocation(name: str, *, attempt: bool = True) -> AllocationToken:
    return AllocationToken(
        allocation_id=name,
        owner=scope().owner,
        scope="attempt" if attempt else "batch",
        attempt_id="attempt" if attempt else None,
        resource_kind=name,
        expected_resource_id="resource-" + name,
        provider_id="unit",
        provider_version="1",
        recovery_ref=reference(recovery(attempt), "recovery-plan/1"),
    )


def baseline_inputs(*, allowed_actions: tuple[str, ...] = ("stop",)) -> BaselineInputs:
    spec = specification()
    spec_ref = reference(spec, "initial-state-spec/1")
    public = PublicTask(
        identity=identity(),
        goal="Read public map",
        start_url="https://map.example/",
        allowed_actions=allowed_actions,
    )
    binding = TaskBinding(
        identity=identity(),
        registration_id="map-unit-1",
        public_task_ref=reference(public, "public-task/1", "public"),
        private_spec_ref=reference({"checks": "unit"}),
        baseline_ref=spec_ref,
    )
    binding_ref = reference(binding, "task-binding/1")
    token = allocation("site", attempt=False)
    env = EnvironmentBaseline(
        scope=scope(),
        operation=op("environment", allocation=token.allocation_id),
        allocation=token,
        spec_ref=spec_ref,
        checks=checks(spec.environment_checks),
        measured_state_sha256="1" * 64,
    )
    env_ref = reference(env, "environment-baseline/1")
    recovery_ref = reference(recovery(True), "recovery-plan/1")
    prep = PreparationReceipt(
        scope=scope(),
        operation=op("prepare", recovery=recovery_ref),
        task_binding_ref=binding_ref,
        spec_ref=spec_ref,
        environment_ref=env_ref,
        recovery_ref=recovery_ref,
        checks=checks(spec.preparation_checks),
    )
    prep_ref = reference(prep, "preparation-receipt/1")
    prepared = PreparedTask(
        scope=scope(),
        public_task=public,
        task_binding_ref=binding_ref,
        spec_ref=spec_ref,
        preparation_ref=prep_ref,
        private_checks_ref=binding.private_spec_ref,
        recovery_ref=recovery_ref,
    )
    prepared_ref = reference(prepared, "prepared-task/1")
    observation = sample_observation(identity(), attempt_id="attempt")
    observation_ref = reference(observation, "observation/1", "public")
    initial = InitialStateChecks(
        scope=scope(),
        operation=op("initial"),
        spec_ref=spec_ref,
        prepared_ref=prepared_ref,
        observation_ref=observation_ref,
        checks=checks(spec.initial_checks),
        measured_state_sha256="2" * 64,
    )
    return BaselineInputs(
        binding=binding,
        public_task=public,
        spec=spec,
        spec_ref=spec_ref,
        environment=env,
        environment_ref=env_ref,
        preparation=prep,
        preparation_ref=prep_ref,
        prepared=prepared,
        prepared_ref=prepared_ref,
        observation=observation,
        observation_ref=observation_ref,
        initial=initial,
        initial_ref=reference(initial, "initial-state-checks/1"),
    )


def reset_inputs() -> ResetInputs:
    spec = specification()
    task_recovery = recovery(True)
    environment_recovery = recovery(False)
    plan = ResetPlan(
        scope=scope(),
        parent_operation_id="original-execution",
        spec_ref=reference(spec, "initial-state-spec/1"),
        task_recovery_ref=reference(task_recovery, "recovery-plan/1"),
        environment_recovery_ref=reference(environment_recovery, "recovery-plan/1"),
        attempt_allocations=(allocation("browser"), allocation("collector")),
    )
    closures = tuple(
        ClosureReceipt(
            token=t,
            operation_id="close-" + t.allocation_id,
            status="closed",
            evidence=(reference({"closed": t.allocation_id}),),
        )
        for t in plan.attempt_allocations
    )
    refs = tuple(reference(c, "closure-receipt/1") for c in closures)
    task = TaskResetReceipt(
        scope=scope(),
        operation=op("reset-task", cleanup=True, recovery=plan.task_recovery_ref),
        recovery_ref=plan.task_recovery_ref,
        after_closure_refs=refs,
        checks=checks(spec.task_reset_checks),
    )
    task_ref = reference(task, "task-reset/1")
    env = EnvironmentResetReceipt(
        scope=scope(),
        operation=op(
            "reset-environment", cleanup=True, recovery=plan.environment_recovery_ref
        ),
        recovery_ref=plan.environment_recovery_ref,
        after_task_reset_ref=task_ref,
        checks=checks(spec.environment_reset_checks),
    )
    env_ref = reference(env, "environment-reset/1")
    health = ResetHealthReceipt(
        scope=scope(),
        operation=op("reset-health", cleanup=True),
        after_environment_reset_ref=env_ref,
        checks=checks(spec.health_checks),
    )
    return ResetInputs(
        plan=plan,
        plan_ref=reference(plan, "reset-plan/1"),
        spec=spec,
        task_recovery=task_recovery,
        environment_recovery=environment_recovery,
        closures=closures,
        closure_refs=refs,
        task=task,
        task_ref=task_ref,
        environment=env,
        environment_ref=env_ref,
        health=health,
        health_ref=reference(health, "reset-health/1"),
    )
