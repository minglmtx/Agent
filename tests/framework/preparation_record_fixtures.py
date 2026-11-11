"""Engineering-only immutable facts, actual filesystem store and mocked native worker."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    RecoveryPlan,
    AllocationToken,
)
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.state_checks import InitialStateSpec, StateChecks
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparationInputs,
)
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.sites.shopping_admin.tasks.product_preparation_checks import (
    ProductPreparationChecks,
    PRODUCT_PREPARATION_CHECKS,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_execution import (
    ProductExecutionInput,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_recovery_contract import (
    ProductRecoverySnapshot,
)
from evidence_control_fixtures import EvidenceFixtureStore
from test_run_journal import CancelSwitch
from test_site_task_execution import request
from test_admin_description_inputs import public_task, FIXTURE
from test_admin_product_seed import SEED_FILE
from test_product_recovery_rpc import case
from site_worker_fixtures import configuration
from test_slurm_commands import guard


class Authority:
    def __init__(self) -> None:
        self.calls = 0
        self.denied = False

    def verify(
        self,
        inputs: PreparationInputs,
        checks: StateChecks,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if self.denied:
            raise PermissionError("engineering authority denied")

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
        if self.denied:
            raise PermissionError("engineering binding denied")


@dataclass
class Case:
    store: EvidenceFixtureStore
    adapter: EvidencePreparationRecords
    authority: Authority
    selection: PreparationSelection
    request: SiteTaskRequest
    result: SiteTaskResult
    environment: EnvironmentBaseline
    snapshot: ProductRecoverySnapshot

    def put(self, value: Contract, visibility: str = "private") -> EvidenceRef:
        return put(self.store, value, visibility)


def put(
    store: EvidenceFixtureStore, value: Contract, visibility: Any = "private"
) -> EvidenceRef:
    return store.put(
        value.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=str(value.model_dump()["schema_version"]),
            visibility=visibility,
            producer="unit",
        ),
        control=guard(),
    )


def fixture(
    root: Path,
    *,
    store: EvidenceFixtureStore | None = None,
    site_token: AllocationToken | None = None,
    start_url: str | None = None,
    initial_checks: tuple[str, ...] = ("initial",),
) -> Case:
    if store is None:
        (root / "evidence").mkdir()
        store = EvidenceFixtureStore(root / "evidence")
    original = request()
    data = ProductExecutionInput.model_validate_json(original.private_input)
    native = store.put(
        FIXTURE.read_bytes(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="admin-native-contract/1",
            visibility="private",
            producer="unit",
        ),
        control=guard(),
    )
    seed = store.put(
        SEED_FILE.read_bytes(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="admin-product-fixture/1",
            visibility="private",
            producer="unit",
        ),
        control=guard(),
    )
    data = data.model_copy(
        update={
            "spec": data.spec.model_copy(update={"native_contract_ref": native}),
            "seed": data.seed.model_copy(update={"reference": seed}),
        }
    )
    spec = InitialStateSpec(
        spec_id="product-initial",
        task=original.task,
        environment_checks=("environment",),
        preparation_checks=PRODUCT_PREPARATION_CHECKS,
        initial_checks=initial_checks,
        equivalence_checks=("equivalence",),
        task_reset_checks=("task-reset",),
        environment_reset_checks=("environment-reset",),
        health_checks=("health",),
    )
    spec_ref = put(store, spec)
    binding = TaskBinding(
        identity=original.task,
        registration_id="admin-product",
        public_task_ref=put(
            store,
            public_task(**({"start_url": start_url} if start_url else {})),
            "public",
        ),
        private_spec_ref=put(store, data.spec),
        baseline_ref=spec_ref,
    )
    binding_ref = put(store, binding)
    token = site_token or configuration().token.model_copy(
        update={"expected_resource_id": "test-instance"}
    )
    recovery = RecoveryPlan(
        recovery_id="product-recovery",
        owner=token.owner,
        attempt_id="attempt",
        baseline_ref=spec_ref,
        restore_component_id="admin-product",
        restore_component_version="3",
        state_coverage=spec.task_reset_checks,
    )
    recovery_ref = put(store, recovery)
    env_recovery = (
        site_token.recovery_ref
        if site_token is not None
        else put(
            store,
            recovery.model_copy(
                update={
                    "recovery_id": "environment-recovery",
                    "attempt_id": None,
                    "state_coverage": spec.environment_reset_checks,
                }
            ),
        )
    )
    token = token.model_copy(update={"recovery_ref": env_recovery})
    operation = original.operation.model_copy(update={"recovery_ref": recovery_ref})
    snapshot_request = original.model_copy(
        update={
            "binding_ref": binding_ref,
            "private_input": data.model_dump_json(),
            "action": "snapshot",
            "snapshot_ref": None,
            "operation": operation.model_copy(update={"operation_id": "snapshot"}),
        }
    )
    worker, _ = case(root / "site")
    saved = worker.execute_task(snapshot_request, control=guard())
    snapshot = ProductRecoverySnapshot.model_validate_json(saved.private_result)
    original = original.model_copy(
        update={
            "binding_ref": binding_ref,
            "private_input": data.model_dump_json(),
            "operation": operation,
            "snapshot_ref": put(store, snapshot),
        }
    )
    result = worker.execute_task(original, control=guard())
    env = EnvironmentBaseline(
        scope=StateScope(
            owner=token.owner,
            task=original.task,
            attempt_id="attempt",
            context_id="context",
        ),
        operation=operation.model_copy(
            update={"operation_id": "environment", "recovery_ref": env_recovery}
        ),
        allocation=token,
        spec_ref=spec_ref,
        checks=StateChecks(required=spec.environment_checks),
        measured_state_sha256="0" * 64,
    )
    selection = PreparationSelection(
        request_ref=put(store, original),
        result_ref=put(store, result),
        environment_ref=put(store, env),
    )
    auth = Authority()
    controls = OperationGuards(SystemClock(), CancelSwitch())
    bindings = EvidenceTaskBindings(store, controls, auth)
    adapter = EvidencePreparationRecords(
        store, controls, bindings, ProductPreparationChecks(store), auth
    )
    return Case(store, adapter, auth, selection, original, result, env, snapshot)
