"""Task/Capture/Restore in one original Shopping worker; no repeated effects."""

from collections.abc import Callable
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from ..instance import ShoppingInstance
from .order_eta_native import OrderEtaNative
from .order_eta_state import OrderEtaState
from .order_eta_recovery import OrderEtaRecoverySnapshot, OrderEtaRestored
from .order_eta_admission import task_input, same_snapshot
from .order_eta_validation import validate_eta_initialization


class OrderEtaLifecycle:
    def __init__(
        self, instance: ShoppingInstance, customer: Callable[[OperationControl], str]
    ) -> None:
        self.instance = instance
        self.native = OrderEtaNative(instance, customer)
        self.phase = "new"
        self.busy = False
        self.operations: set[str] = set()
        self.snapshot: OrderEtaRecoverySnapshot | None = None
        self.snapshot_ref: EvidenceRef | None = None
        self.preparation: SiteTaskRequest | None = None
        self.prepared: OrderEtaState | None = None
        self.restore_request: SiteTaskRequest | None = None
        self.restore_result: SiteTaskResult | None = None

    def _original(self, request: SiteTaskRequest) -> None:
        if self.snapshot is None:
            raise InvalidTransition(
                "Shopping task requires original completed snapshot"
            )
        self.snapshot_ref = same_snapshot(request, self.snapshot, self.snapshot_ref)
        if request.action == "restore":
            parent = self.preparation or self.snapshot.request
            if request.operation.parent_operation_id != parent.operation.operation_id:
                raise OwnershipConflict(
                    "Shopping restore changed original preparation parent"
                )

    def _available(self, operation_id: str) -> None:
        if (
            self.busy
            or self.phase in ("quarantined", "restored")
            or operation_id in self.operations
        ):
            raise InvalidTransition(
                "Shopping task busy, finished, unknown or operation reused"
            )

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        data = task_input(request)
        self._available(request.operation.operation_id)
        if request.action == "snapshot":
            if self.phase != "new":
                raise InvalidTransition("Shopping snapshot already attempted")
        else:
            self._original(request)
            if (
                (request.action == "prepare" and self.phase != "snapshotted")
                or (request.action == "inspect" and self.phase != "prepared")
                or (
                    request.action == "restore"
                    and self.phase not in ("snapshotted", "prepared")
                )
            ):
                raise InvalidTransition(
                    "Shopping task phase does not permit this operation"
                )
        control.checkpoint()
        self.operations.add(request.operation.operation_id)
        self.busy = True
        try:
            if request.action == "snapshot":
                self.phase = "snapshotting"
                before = self.native.protected(control)
                saved = self.instance.snapshot_and_restart(control)
                self.snapshot = OrderEtaRecoverySnapshot(
                    request=request, state=saved, protected=before
                )
                payload = self.snapshot.model_dump_json()
                self.phase = "snapshotted"
            elif request.action == "restore":
                assert self.snapshot is not None
                self.phase = "restoring"
                inventory = self.instance.restore(self.snapshot.state, control)
                stopped = self.instance.generations[-1].quiescence
                assert stopped is not None
                payload = OrderEtaRestored(
                    request=request,
                    snapshot=self.snapshot,
                    stopped=stopped,
                    inventory=inventory,
                ).model_dump_json()
                self.phase = "restored"
            else:
                if request.action == "prepare":
                    self.phase = "preparing"
                    self.preparation = request
                measured = self.native.observe(
                    data.spec, control, initialize=request.action == "prepare"
                )
                if request.action == "prepare":
                    assert self.snapshot is not None
                    validate_eta_initialization(
                        data.spec, self.snapshot.protected, measured
                    )
                    self.prepared = measured
                payload = measured.model_dump_json()
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
            setattr(error, "shopping_recovery_snapshot", self.snapshot)
            setattr(error, "shopping_restored_inventory", self.instance.restored)
            raise
        finally:
            self.busy = False

    def capture_task(
        self, capture: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        capture = SiteCaptureRequest.model_validate(capture)
        if (capture.collector_id, capture.collector_version) != (
            "shopping-order-eta",
            "1",
        ):
            raise ValueError("Unsupported fixed Shopping task collector")
        request = capture.inspection
        data = task_input(request)
        self._available(request.operation.operation_id)
        if self.phase != "prepared":
            raise InvalidTransition("Shopping capture requires original prepared task")
        self._original(request)
        control.checkpoint()
        self.operations.add(request.operation.operation_id)
        self.busy = True
        try:
            measured = self.native.observe(data.spec, control)
            result = SiteTaskResult(
                request_sha256=capture.digest, private_result=measured.model_dump_json()
            )
            control.checkpoint()
            return result
        except BaseException:
            self.phase = "quarantined"
            raise
        finally:
            self.busy = False
