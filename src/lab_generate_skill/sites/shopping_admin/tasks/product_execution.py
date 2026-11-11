"""Fixed selected-family dispatch inside the original supervised site worker.

Input is the exact private spec/fixture, output measured ProductState JSON. No
public observation or BaselineReceipt is produced. One preparation attempt per
instance; reads retain original scope even after an uncertain preparation.
Outer resource/task authority and persistent intent are mandatory, not supplied
by this in-memory duplicate guard. Complete reset must precede another task.
"""

from typing import Literal
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from ..service_contract import AdminServiceSpec
from .product_description_spec import ProductDescriptionSpec
from .product_seed_contract import ProductSeed
from .product_seed import AdminProductSeed


class ProductExecutionInput(Contract):
    schema_version: Literal["admin-product-execution-input/1"] = (
        "admin-product-execution-input/1"
    )
    spec: ProductDescriptionSpec
    seed: ProductSeed


class AdminProductExecution:
    def __init__(self, service: AdminServiceSpec, commands: NativeCommands) -> None:
        self.service, self.commands = service, commands
        self.original: SiteTaskRequest | None = None
        self.worker: AdminProductSeed | None = None
        self.operations: set[str] = set()

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        if request.action not in ("prepare", "inspect"):
            raise ValueError(
                "Product execution accepts only prepare/inspect; use lifecycle for recovery"
            )

        if (request.task.site, request.task.family, request.task.contract_version) != (
            "shopping_admin",
            "product_description",
            1,
        ):
            raise ValueError("Unsupported fixed site/task family")
        data = ProductExecutionInput.model_validate_json(request.private_input)
        if (
            data.model_dump_json() != request.private_input
            or data.spec.task != request.task
            or len(data.seed.scenario.products) != 1
        ):
            raise ValueError(
                "Task input is not canonical, single-product or same identity"
            )
        control.checkpoint()
        if request.operation.operation_id in self.operations:
            raise InvalidTransition("Task operation cannot repeat")
        if request.action == "prepare":
            if self.original is not None:
                raise InvalidTransition(
                    "Preparation already attempted; never reinitialize"
                )
            # Constructor validates fixture/native agreement before recording effects.
            worker = AdminProductSeed(self.service, data.spec, data.seed, self.commands)
            self.original, self.worker = request, worker
        else:
            if self.original is None or self.worker is None:
                raise InvalidTransition(
                    "Inspect requires original attempted preparation"
                )
            old = self.original
            if (
                request.task,
                request.binding_ref,
                request.private_input,
                request.operation.run_id,
                request.operation.owner_id,
                request.operation.attempt_id,
                request.operation.allocation_id,
                request.operation.recovery_ref,
            ) != (
                old.task,
                old.binding_ref,
                old.private_input,
                old.operation.run_id,
                old.operation.owner_id,
                old.operation.attempt_id,
                old.operation.allocation_id,
                old.operation.recovery_ref,
            ):
                raise OwnershipConflict(
                    "Inspect changed original task/binding/recovery"
                )
        self.operations.add(request.operation.operation_id)
        assert self.worker is not None
        state = (
            self.worker.initialize(control)
            if request.action == "prepare"
            else self.worker.inspect(control)
        )
        result = SiteTaskResult(
            request_sha256=request.digest, private_result=state.model_dump_json()
        )
        control.checkpoint()
        return result
