"""Real CAS/native state codecs; synthetic services and record authority."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.bootstrap.admin_navigation import (
    admin_navigation_preparation_records,
)
from lab_generate_skill.domain.lifecycle import RecoveryPlan, AllocationToken
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.preparation_record import PreparationSelection
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.state_checks import InitialStateSpec, StateChecks
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
    NavigationRecoverySnapshot,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_preparation_checks import (
    NAVIGATION_PREPARATION_CHECKS,
)
from evidence_control_fixtures import EvidenceFixtureStore
from preparation_record_fixtures import Authority, put
from admin_navigation_fixtures import case, request
from site_worker_fixtures import configuration
from test_run_journal import CancelSwitch
from test_slurm_commands import guard


@dataclass
class Case:
    store: EvidenceFixtureStore
    adapter: EvidencePreparationRecords
    authority: Authority
    selection: PreparationSelection
    request: SiteTaskRequest
    result: SiteTaskResult
    snapshot: NavigationRecoverySnapshot
    environment: EnvironmentBaseline


def fixture(
    root: Path,
    contracts: Any,
    index: int = 0,
    *,
    store: EvidenceFixtureStore | None = None,
    site_token: AllocationToken | None = None,
    start_url: str | None = None,
    initial_checks: tuple[str, ...] = ("initial",),
) -> Case:
    if store is None:
        (root / "evidence").mkdir()
        store = EvidenceFixtureStore(root / "evidence")
    native, ref, public = contracts[index]
    if start_url is not None:
        public = public.model_copy(update={"start_url": start_url})
    data = NavigationExecutionInput(
        spec=bind_admin_navigation(native, ref, public).private_spec
    )
    original = request(contracts[index:])
    spec = InitialStateSpec(
        spec_id="unit-navigation-preparation",
        task=public.identity,
        environment_checks=("environment",),
        preparation_checks=NAVIGATION_PREPARATION_CHECKS,
        initial_checks=initial_checks,
        equivalence_checks=("equivalence",),
        task_reset_checks=("full-task-reset",),
        environment_reset_checks=("environment-reset",),
        health_checks=("health",),
    )
    spec_ref = put(store, spec)
    binding = TaskBinding(
        identity=public.identity,
        registration_id="admin-navigation",
        public_task_ref=put(store, public, "public"),
        private_spec_ref=put(store, data.spec),
        baseline_ref=spec_ref,
    )
    binding_ref = put(store, binding)
    worker, _ = case(root / "site")
    token = (site_token or configuration().token).model_copy(
        update={"expected_resource_id": worker.service.layout.instance_id}
    )
    recovery = RecoveryPlan(
        recovery_id="navigation-recovery",
        owner=token.owner,
        attempt_id=original.operation.attempt_id,
        baseline_ref=spec_ref,
        restore_component_id="admin-navigation",
        restore_component_version="1",
        state_coverage=spec.task_reset_checks,
    )
    recovery_ref = put(store, recovery)
    environment_recovery = (
        site_token.recovery_ref
        if site_token is not None
        else put(
            store,
            recovery.model_copy(
                update={
                    "recovery_id": "environment-recovery",
                    "attempt_id": None,
                    "restore_component_id": "admin-frontend",
                    "state_coverage": spec.environment_reset_checks,
                }
            ),
        )
    )
    token = token.model_copy(update={"recovery_ref": environment_recovery})
    original = original.model_copy(
        update={
            "binding_ref": binding_ref,
            "private_input": data.model_dump_json(),
            "operation": original.operation.model_copy(
                update={"recovery_ref": recovery_ref}
            ),
        }
    )
    saved = worker.execute_task(original, control=guard())
    snapshot = NavigationRecoverySnapshot.model_validate_json(saved.private_result)
    prepared = original.model_copy(
        update={
            "action": "prepare",
            "snapshot_ref": put(store, snapshot),
            "operation": original.operation.model_copy(
                update={"operation_id": "navigation-prepare"}
            ),
        }
    )
    result = worker.execute_task(prepared, control=guard())
    environment = EnvironmentBaseline(
        scope=StateScope(
            owner=token.owner,
            task=public.identity,
            attempt_id="attempt",
            context_id="context",
        ),
        operation=prepared.operation.model_copy(
            update={"operation_id": "environment", "recovery_ref": environment_recovery}
        ),
        allocation=token,
        spec_ref=spec_ref,
        checks=StateChecks(required=spec.environment_checks),
        measured_state_sha256=snapshot.state.digest,
    )
    selection = PreparationSelection(
        request_ref=put(store, prepared),
        result_ref=put(store, result),
        environment_ref=put(store, environment),
    )
    authority = Authority()
    controls = OperationGuards(SystemClock(), CancelSwitch())
    bindings = EvidenceTaskBindings(store, controls, authority)
    return Case(
        store,
        admin_navigation_preparation_records(store, controls, bindings, authority),
        authority,
        selection,
        prepared,
        result,
        snapshot,
        environment,
    )
