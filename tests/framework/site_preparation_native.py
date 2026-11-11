"""Receipt integration with actual registered worker; engineering-only policy.

Environment coverage deliberately remains unknown. This helper cannot make a
BaselineReceipt ready or authorize Actor/model execution.
"""

from typing import Any
from urllib.parse import urlsplit
import json
from datetime import datetime, timezone
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparationInputs,
)
from lab_generate_skill.domain.preparation import (
    EnvironmentBaseline,
    PreparationReceipt,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.state_checks import InitialStateSpec, StateChecks
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.lifecycle import OperationContext, RecoveryPlan
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.bootstrap.admin_preparation import admin_preparation_records
from lab_generate_skill.bootstrap.admin_description import (
    load_product_description_inputs,
)
from lab_generate_skill.bootstrap.admin_product_seed import load_admin_product_seed
from lab_generate_skill.sites.shopping_admin.tasks.product_execution import (
    ProductExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_state import (
    OrderEtaExecutionInput,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_preparation_checks import (
    PRODUCT_PREPARATION_CHECKS,
)
from site_resource_fixtures import Case
from test_admin_description_inputs import FIXTURE, public_task
from test_admin_product_seed import SEED_FILE
from test_slurm_commands import guard


class NativePreparation:
    data: ProductExecutionInput | OrderEtaExecutionInput
    bindings: TaskBindings
    records: PreparationRecords
    attempt_id = "native-product-attempt"
    context_id = "native-product-context"

    def __init__(
        self,
        c: Case,
        endpoint: str,
        *,
        state_spec: InitialStateSpec | None = None,
        allowed_actions: tuple[str, ...] | None = None,
    ) -> None:
        self.c = c
        self.request: SiteTaskRequest | None = None
        self.result: SiteTaskResult | None = None
        self.environment: EnvironmentBaseline | None = None
        native = self.raw(FIXTURE.read_bytes(), "admin-native-contract/1")
        seed = self.raw(SEED_FILE.read_bytes(), "admin-product-fixture/1")
        origin = urlsplit(endpoint)
        route = str(json.loads(FIXTURE.read_bytes())["start_path"])
        self.public = public_task(
            start_url=origin._replace(
                path=origin.path.rstrip("/") + route, query="", fragment=""
            ).geturl()
        )
        if allowed_actions is not None:
            self.public = PublicTask.model_validate(
                {**self.public.model_dump(), "allowed_actions": allowed_actions}
            )
        self.data = ProductExecutionInput(
            spec=load_product_description_inputs(
                FIXTURE.read_bytes(), native, self.public
            ).private_spec,
            seed=load_admin_product_seed(SEED_FILE.read_bytes(), seed),
        )
        task = self.public.identity
        self.spec = state_spec or InitialStateSpec(
            spec_id="native-product-initial",
            task=task,
            environment_checks=("admin.environment.complete",),
            preparation_checks=PRODUCT_PREPARATION_CHECKS,
            initial_checks=("admin.initial.observation",),
            equivalence_checks=("admin.initial.equivalence",),
            task_reset_checks=("admin.task.reset",),
            environment_reset_checks=("admin.environment.reset",),
            health_checks=("admin.health",),
        )
        self.spec_ref = self.put(self.spec)
        self.binding = TaskBinding(
            identity=task,
            registration_id="engineering-admin-product",
            public_task_ref=self.put(self.public, "public"),
            private_spec_ref=self.put(self.data.spec),
            baseline_ref=self.spec_ref,
        )
        self.bindings = EvidenceTaskBindings(c.evidence, c.controls, self)
        self.binding_ref = self.bindings.publish(self.binding, c.op)
        self.recovery = RecoveryPlan(
            recovery_id="native-product-recovery",
            owner=c.spec.token.owner,
            attempt_id="native-product-attempt",
            baseline_ref=self.spec_ref,
            restore_component_id="admin-product",
            restore_component_version="3",
            state_coverage=self.spec.task_reset_checks,
        )
        self.recovery_ref = self.put(self.recovery)
        self.records = admin_preparation_records(
            c.evidence, c.controls, self.bindings, self
        )

    @property
    def native_contract_ref(self) -> EvidenceRef:
        return self.data.spec.native_contract_ref

    def private_input_json(self) -> str:
        return self.data.model_dump_json()

    def raw(self, data: bytes, schema: str, visibility: Any = "private") -> EvidenceRef:
        return self.c.evidence.put(
            data,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility=visibility,
                producer="native-preparation-engineering",
            ),
            control=guard(10),
        )

    def put(self, value: Contract, visibility: Any = "private") -> EvidenceRef:
        return self.raw(
            value.model_dump_json().encode(),
            str(value.model_dump()["schema_version"]),
            visibility,
        )

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
        assert binding == self.binding and public_task == self.public
        assert (
            private_spec == self.data.spec.model_dump_json().encode()
            and baseline == self.spec.model_dump_json().encode()
        )

    def verify(
        self,
        inputs: PreparationInputs,
        checks: StateChecks,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert (
            inputs.request == self.request
            and inputs.result == self.result
            and inputs.environment == self.environment
        )
        assert checks.status == "pass"
        assert (
            self.c.journal.read(
                self.c.spec.token, self.resource_read_operation(op)
            ).state
            == "acquired"
        )

    def resource_read_operation(self, op: OperationContext) -> OperationContext:
        # Task attempt/recovery differ from batch resource ownership. Retain the
        # caller deadline but read the original batch token with its own scope.
        return self.c.op.model_copy(
            update={
                "operation_id": "prepare-resource-" + op.operation_id,
                "deadline": op.deadline,
                "mode": "cleanup",
                "parent_operation_id": self.c.op.operation_id,
                "cancellation_ref": None,
            }
        )

    def publish(
        self,
        request: SiteTaskRequest,
        result: SiteTaskResult,
        started: SiteInstanceStarted,
        *,
        environment: EnvironmentBaseline | None = None,
    ) -> dict[str, Any]:
        self.request, self.result = request, result
        assert started.files == self.c.spec.configuration.files
        self.environment = environment or EnvironmentBaseline(
            scope=StateScope(
                owner=self.c.spec.token.owner,
                task=request.task,
                attempt_id="native-product-attempt",
                context_id="native-product-context",
            ),
            operation=request.operation.model_copy(
                update={
                    "operation_id": "native-environment-record",
                    "recovery_ref": self.c.spec.token.recovery_ref,
                }
            ),
            allocation=self.c.spec.token,
            spec_ref=self.spec_ref,
            checks=StateChecks(required=self.spec.environment_checks),
            measured_state_sha256=started.files.image.sha256,
        )
        selection = PreparationSelection(
            request_ref=self.put(request),
            result_ref=self.put(result),
            environment_ref=self.put(self.environment),
        )
        # Independent bounded publication, original historical request retained.
        op = request.operation.cleanup(
            "native-prepare-record", now=datetime.now(timezone.utc), seconds=30
        )
        publication = self.records.publish(selection, op)
        prepared = self.records.load(publication, op)
        receipt = PreparationReceipt.model_validate_json(
            self.c.evidence.read(publication.preparation_ref, control=guard(10))
        )
        assert prepared.public_task == self.public and receipt.checks.status == "pass"
        assert (
            self.environment.scope.task == request.task
            and self.environment.spec_ref == self.spec_ref
        )
        assert self.environment.allocation == self.c.spec.token
        assert self.environment.checks.status == (
            "unknown" if environment is None else "pass"
        )
        return dict(
            publication=publication.model_dump(mode="json"),
            preparation=receipt.model_dump(mode="json"),
            prepared=prepared.model_dump(mode="json"),
            environment_status=self.environment.checks.status,
            actor_authorized=False,
        )
