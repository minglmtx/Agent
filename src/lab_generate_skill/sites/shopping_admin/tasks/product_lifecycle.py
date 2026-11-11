"""Original worker snapshot -> prepare/inspect -> cleanup restore.

Parent must persist the returned exact snapshot and verify actual permissions
before prepare. This local lifecycle validates its reference and never creates a
replacement baseline. Restored covers DB/declared files/cache/search/product absence;
external effects and whole-site ResetReceipt remain external gates. No
new task is accepted merely because this partial scope restored successfully.
"""

import hashlib
from collections.abc import Callable
from ..frontend_contract import AdminFrontendStopped
from typing import Literal
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from ..product_catalog import capture_product_catalog
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from ..service_contract import AdminServiceSpec
from ..service_commands import container
from ..state import AdminState
from ..state_contract import AdminStatePlan
from ..artifact_contract import AdminArtifactLayout, ARTIFACT_PATHS
from .product_execution import AdminProductExecution, ProductExecutionInput
from .product_seed import AdminProductSeed
from .product_recovery_contract import (
    ProductAbsence,
    ProductRecoverySnapshot,
    ProductRestored,
)
from .product_recovery_authority import ProductRecoveryAuthority
from .product_search_authority import ProductSearchAuthority
from .product_restore_program import PRODUCT_ABSENCE_PHP


class AdminProductLifecycle:
    def __init__(
        self,
        service: AdminServiceSpec,
        commands: NativeCommands,
        stop_frontend: Callable[[OperationControl], AdminFrontendStopped],
    ) -> None:
        self.service = AdminServiceSpec.model_validate(service)
        self.commands = commands
        self.stop_frontend = stop_frontend
        self.frontend_stopped: AdminFrontendStopped | None = None
        layout = self.service.layout
        plan = AdminStatePlan(
            service=service,
            artifacts=AdminArtifactLayout(
                instance_id=layout.instance_id,
                node_root=layout.node_root,
                app_root=layout.state_root + "/app",
                backup_root=layout.node_root + "/task-state-backup",
                paths=tuple(sorted(ARTIFACT_PATHS)),
            ),
        )
        self.authority = ProductRecoveryAuthority(plan)
        self.state = AdminState(
            plan, commands, self.authority, ProductSearchAuthority(self.authority)
        )
        self.product = AdminProductExecution(service, commands)
        self.snapshot: ProductRecoverySnapshot | None = None
        self.snapshot_ref: EvidenceRef | None = None
        self.preparation: SiteTaskRequest | None = None
        self.restore_result: SiteTaskResult | None = None
        self.restore_request: SiteTaskRequest | None = None
        self.phase: Literal[
            "new",
            "snapshotting",
            "snapshotted",
            "preparing",
            "prepared",
            "restoring",
            "restored",
            "quarantined",
        ] = "new"
        self.busy = False
        self.operations: set[str] = set()

    def _absence(
        self, data: ProductExecutionInput, control: OperationControl
    ) -> ProductAbsence:
        raw = self.commands.run(
            container(self.service)
            + ("php", "-r", PRODUCT_ABSENCE_PHP, str(data.spec.product_id)),
            control,
        )
        result = ProductAbsence.model_validate_json(raw)
        if (
            raw != result.model_dump_json().encode()
            or result.product_id != data.spec.product_id
            or not result.absent
        ):
            error = ValueError("Original product absence is not established")
            setattr(error, "product_absence_reply", raw)
            raise error
        return result

    def _original(self, request: SiteTaskRequest) -> None:
        if self.snapshot is None:
            raise InvalidTransition("Task requires original completed snapshot")
        old = self.snapshot.request
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
                "Task changed original snapshot scope or private input"
            )
        ref = request.snapshot_ref
        raw = self.snapshot.model_dump_json().encode()
        if (
            ref is None
            or (ref.content_schema, ref.sha256, ref.size_bytes)
            != (self.snapshot.schema_version, hashlib.sha256(raw).hexdigest(), len(raw))
            or (self.snapshot_ref is not None and ref != self.snapshot_ref)
        ):
            raise OwnershipConflict(
                "Task did not retain exact persisted original snapshot"
            )
        if request.action == "restore":
            parent = self.preparation or old
            if request.operation.parent_operation_id != parent.operation.operation_id:
                raise OwnershipConflict("Restore changed original preparation parent")
        self.snapshot_ref = ref

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        data = ProductExecutionInput.model_validate_json(request.private_input)
        if (
            data.model_dump_json() != request.private_input
            or data.spec.task != request.task
        ):
            raise ValueError("Lifecycle requires canonical original task input")
        AdminProductSeed(
            self.service, data.spec, data.seed, self.commands
        )  # pure fixture compatibility before effects
        if (
            self.busy
            or self.phase in ("quarantined", "restored")
            or request.operation.operation_id in self.operations
        ):
            raise InvalidTransition(
                "Task lifecycle busy, finished, quarantined or operation repeated"
            )
        if request.action == "snapshot":
            if self.phase != "new":
                raise InvalidTransition("Snapshot already attempted")
        else:
            self._original(request)
            if request.action == "prepare" and self.phase != "snapshotted":
                raise InvalidTransition(
                    "Prepare requires the original unconsumed snapshot"
                )
            if request.action == "inspect" and self.phase != "prepared":
                raise InvalidTransition("Inspect requires original prepared task")
            if request.action == "restore" and self.phase not in (
                "snapshotted",
                "prepared",
            ):
                raise InvalidTransition(
                    "Restore requires original live snapshotted instance"
                )
        control.checkpoint()
        self.busy = True
        self.operations.add(request.operation.operation_id)
        self.authority.current = request
        try:
            if request.action == "snapshot":
                self.phase = "snapshotting"
                absence = self._absence(data, control)
                saved = self.state.save(control)
                self.snapshot = ProductRecoverySnapshot(
                    request=request, state=saved, product=absence
                )
                self.authority.snapshot = saved
                payload = self.snapshot.model_dump_json()
                self.phase = "snapshotted"
            elif request.action == "restore":
                self.phase = "restoring"
                assert self.snapshot is not None and request.snapshot_ref is not None
                self.frontend_stopped = AdminFrontendStopped.model_validate(
                    self.stop_frontend(control)
                )
                if self.frontend_stopped.service != self.service:
                    raise OwnershipConflict("Frontend closure changed original service")
                restored = self.state.restore(self.snapshot.state, control)
                absence = self._absence(data, control)
                payload = ProductRestored(
                    task=request.task,
                    operation=request.operation,
                    snapshot_ref=request.snapshot_ref,
                    state=restored,
                    frontend=self.frontend_stopped,
                    product=absence,
                ).model_dump_json()
                self.phase = "restored"
            else:
                if request.action == "prepare":
                    self.preparation = request
                    self.phase = "preparing"
                payload = self.product.execute_task(
                    request, control=control
                ).private_result
                self.phase = "prepared"
            result = SiteTaskResult(
                request_sha256=request.digest, private_result=payload
            )
            if request.action == "restore":
                self.restore_request, self.restore_result = request, result
            control.checkpoint()
            return result
        except BaseException as error:
            self.phase = "quarantined"
            setattr(error, "admin_product_recovery_snapshot", self.snapshot)
            setattr(error, "admin_frontend_stopped", self.frontend_stopped)
            raise
        finally:
            self.busy = False
            self.authority.current = None

    def capture_task(
        self, capture: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        capture = SiteCaptureRequest.model_validate(capture)
        request = capture.inspection
        if (capture.collector_id, capture.collector_version) != (
            "admin-product-catalog",
            "1",
        ):
            raise ValueError("Unsupported fixed product collector")
        if (
            self.busy
            or self.phase != "prepared"
            or request.operation.operation_id in self.operations
        ):
            raise InvalidTransition(
                "Capture requires original prepared, idle task and unused operation"
            )
        self._original(request)
        data = ProductExecutionInput.model_validate_json(request.private_input)
        control.checkpoint()
        self.busy = True
        self.operations.add(request.operation.operation_id)
        try:
            state = capture_product_catalog(
                self.service, data.spec.product_id, self.commands, control
            )
            result = SiteTaskResult(
                request_sha256=capture.digest, private_result=state.model_dump_json()
            )
            control.checkpoint()
            return result
        except BaseException:
            self.phase = "quarantined"
            raise
        finally:
            self.busy = False
