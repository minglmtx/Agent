"""Navigation native worker state, reusing the complete Admin state backend.

No product seed or fabricated target is involved. The browser's declared local
start is a separate admitted step. Original parent/worker task authority must
admit each request before this delegated worker-local state machine is reached.
"""

from collections.abc import Callable
import hashlib
from typing import Literal
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from ..artifact_contract import AdminArtifactLayout, ARTIFACT_PATHS
from ..frontend_contract import AdminFrontendStopped
from ..service_contract import AdminServiceSpec
from ..state import AdminState
from ..state_contract import AdminStatePlan
from .product_recovery_authority import ProductRecoveryAuthority
from .navigation_search_authority import NavigationSearchAuthority
from .navigation_contents import measure_navigation_contents
from .navigation_integrity import NavigationSnapshotIntegrity
from .navigation_recovery_contract import (
    NavigationExecutionInput,
    NavigationRecoverySnapshot,
    NavigationPrepared,
    NavigationRestored,
)


class AdminNavigationLifecycle:
    def __init__(
        self,
        service: AdminServiceSpec,
        commands: NativeCommands,
        stop_frontend: Callable[[OperationControl], AdminFrontendStopped],
    ) -> None:
        self.service = AdminServiceSpec.model_validate(service)
        self.commands = commands
        self.stop_frontend = stop_frontend
        layout = self.service.layout
        plan = AdminStatePlan(
            service=self.service,
            artifacts=AdminArtifactLayout(
                instance_id=layout.instance_id,
                node_root=layout.node_root,
                app_root=layout.state_root + "/app",
                backup_root=layout.node_root + "/task-state-backup",
                paths=tuple(sorted(ARTIFACT_PATHS)),
            ),
        )
        # These existing guards bind plan/current action/saved snapshot only;
        # they contain no product identity or product-creation permission.
        self.authority = ProductRecoveryAuthority(plan)
        self.state = AdminState(
            plan, commands, self.authority, NavigationSearchAuthority(self.authority)
        )
        self.snapshot: NavigationRecoverySnapshot | None = None
        self.snapshot_ref: EvidenceRef | None = None
        self.preparation: SiteTaskRequest | None = None
        self.restore_request: SiteTaskRequest | None = None
        self.restore_result: SiteTaskResult | None = None
        self.frontend_stopped: AdminFrontendStopped | None = None
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
        self.integrity_attempted = False

    def _original(self, request: SiteTaskRequest) -> None:
        if self.snapshot is None:
            raise InvalidTransition("Navigation requires completed original snapshot")
        old = self.snapshot.request
        for name in ("task", "binding_ref", "private_input"):
            if getattr(request, name) != getattr(old, name):
                raise OwnershipConflict(
                    "Navigation changed original task/binding/input"
                )
        for name in (
            "run_id",
            "owner_id",
            "attempt_id",
            "allocation_id",
            "recovery_ref",
        ):
            if getattr(request.operation, name) != getattr(old.operation, name):
                raise OwnershipConflict("Navigation changed original native scope")
        raw = self.snapshot.model_dump_json().encode()
        reference = request.snapshot_ref
        if (
            reference is None
            or (reference.content_schema, reference.sha256, reference.size_bytes)
            != (self.snapshot.schema_version, hashlib.sha256(raw).hexdigest(), len(raw))
            or (self.snapshot_ref is not None and reference != self.snapshot_ref)
        ):
            raise OwnershipConflict("Navigation changed persisted original snapshot")
        if request.action == "restore":
            parent = self.preparation or old
            if request.operation.parent_operation_id != parent.operation.operation_id:
                raise OwnershipConflict("Navigation restore changed original parent")
        self.snapshot_ref = reference

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        data = NavigationExecutionInput.model_validate_json(request.private_input)
        if (
            data.model_dump_json() != request.private_input
            or data.spec.task != request.task
        ):
            raise ValueError("Navigation requires canonical same-task input")
        if request.action not in ("snapshot", "prepare", "restore"):
            raise ValueError(
                "Navigation has no live native inspect; page capture is separate"
            )
        if (
            self.busy
            or self.phase in ("quarantined", "restored")
            or request.operation.operation_id in self.operations
        ):
            raise InvalidTransition(
                "Navigation is busy, finished, quarantined or repeated"
            )
        if request.action == "snapshot":
            if self.phase != "new":
                raise InvalidTransition("Navigation snapshot already attempted")
        else:
            self._original(request)
            if request.action == "prepare" and self.phase != "snapshotted":
                raise InvalidTransition(
                    "Navigation prepare requires unconsumed snapshot"
                )
            if request.action == "restore" and self.phase not in (
                "snapshotted",
                "prepared",
            ):
                raise InvalidTransition(
                    "Navigation restore requires original live snapshot"
                )
        control.checkpoint()
        self.busy = True
        self.operations.add(request.operation.operation_id)
        self.authority.current = request
        try:
            if request.action == "snapshot":
                self.phase = "snapshotting"
                saved = self.state.save(control)
                self.authority.snapshot = saved
                try:
                    contents = measure_navigation_contents(
                        saved, self.commands, control
                    )
                except BaseException as error:
                    setattr(error, "admin_navigation_state_snapshot", saved)
                    raise
                self.snapshot = NavigationRecoverySnapshot(
                    request=request, state=saved, contents=contents
                )
                payload = self.snapshot.model_dump_json()
                self.phase = "snapshotted"
            elif request.action == "prepare":
                assert self.snapshot is not None and request.snapshot_ref is not None
                self.preparation = request
                self.phase = "preparing"
                payload = NavigationPrepared(
                    task=request.task,
                    snapshot_ref=request.snapshot_ref,
                    private_spec_sha256=hashlib.sha256(
                        data.spec.model_dump_json().encode()
                    ).hexdigest(),
                    state_snapshot_sha256=self.snapshot.state.digest,
                    initialization=data.spec.initialization,
                    start_path=data.spec.start_path,
                ).model_dump_json()
                self.phase = "prepared"
            else:
                assert self.snapshot is not None and request.snapshot_ref is not None
                self.phase = "restoring"
                self.frontend_stopped = AdminFrontendStopped.model_validate(
                    self.stop_frontend(control)
                )
                if self.frontend_stopped.service != self.service:
                    raise OwnershipConflict(
                        "Navigation frontend belongs to another instance"
                    )
                restored = self.state.restore(self.snapshot.state, control)
                payload = NavigationRestored(
                    task=request.task,
                    operation=request.operation,
                    snapshot_ref=request.snapshot_ref,
                    state=restored,
                    frontend=self.frontend_stopped,
                ).model_dump_json()
                self.phase = "restored"
            result = SiteTaskResult(
                request_sha256=request.digest, private_result=payload
            )
            if request.action == "restore":
                self.restore_request, self.restore_result = request, result
            control.checkpoint()
            return result
        except BaseException as error:
            self.phase = "quarantined"
            setattr(error, "admin_navigation_recovery_snapshot", self.snapshot)
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
            "admin-navigation-snapshot-integrity",
            "1",
        ):
            raise ValueError(
                "Navigation page facts require the browser collector; only fixed recovery verification is native"
            )
        if (
            self.busy
            or self.phase != "prepared"
            or self.integrity_attempted
            or request.operation.operation_id in self.operations
        ):
            raise InvalidTransition(
                "Navigation integrity requires original prepared task and one unused guard"
            )
        self._original(request)
        assert self.snapshot is not None and request.snapshot_ref is not None
        if self.snapshot.contents is None:
            raise InvalidTransition(
                "Navigation guard requires measured original recovery"
            )
        control.checkpoint()
        self.busy = True
        self.integrity_attempted = True
        self.operations.add(request.operation.operation_id)
        database = None
        artifacts = None
        returned = None
        self.authority.current = request
        try:
            saved = self.snapshot.state
            database = self.state.database.verify(saved.database, control)
            self.state.artifacts.verify(saved.artifacts, control)
            artifacts = saved.artifacts
            self.state.search.verify(saved.search, control)
            proof = NavigationSnapshotIntegrity(
                task=request.task,
                operation=request.operation,
                snapshot_ref=request.snapshot_ref,
                state_snapshot_sha256=saved.digest,
                database=database,
                artifacts=artifacts,
                search=saved.search,
            )
            proof.require_original(self.snapshot)
            returned = SiteTaskResult(
                request_sha256=capture.digest, private_result=proof.model_dump_json()
            )
            control.checkpoint()
            return returned
        except BaseException as error:
            self.phase = "quarantined"
            setattr(error, "admin_navigation_integrity_database", database)
            setattr(error, "admin_navigation_integrity_artifacts", artifacts)
            setattr(error, "admin_navigation_integrity_returned_result", returned)
            setattr(error, "admin_navigation_recovery_snapshot", self.snapshot)
            raise
        finally:
            self.busy = False
            self.authority.current = None
