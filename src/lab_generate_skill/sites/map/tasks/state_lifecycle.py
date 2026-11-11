"""Original Map task through existing Task/Capture ports; no legacy runner.

Outer task admission and browser closure precede restore. This is the original
unchanged-state/Rails reset path, not a DB copy or permission to clear mutations.
"""

import hashlib
import json
import os
import threading
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_state_artifacts import MapStateArtifacts
from ..frontend_reset import MapFrontendReset
from ..state_guard import MapStateGuard, MapGuardObservation
from .state_admission import snapshot_reference, check_native
from .state_codec import MapTaskStateCodec, MapSnapshot


class MapTaskLifecycle:
    def __init__(
        self,
        guard: MapStateGuard,
        reset: MapFrontendReset,
        artifacts: MapStateArtifacts,
        codecs: MapTaskStateCodec,
    ) -> None:
        if reset.guard is not guard or guard.state != "ready" or reset.state != "new":
            raise ValueError(
                "Original healthy guard and unattempted Map reset required"
            )
        self.guard, self.reset, self.artifacts = guard, reset, artifacts
        if not isinstance(codecs, MapTaskStateCodec):
            raise ValueError("Explicit original Map task codec required")
        self.codecs = codecs
        self.owner = os.getpid(), threading.get_ident()
        self.phase = "new"
        self.busy = False
        self.operations: set[str] = set()
        self.snapshot: MapSnapshot | None = None
        self.snapshot_ref: EvidenceRef | None = None
        self.preparation: SiteTaskRequest | None = None
        self.restore_request: SiteTaskRequest | None = None
        self.restore_result: SiteTaskResult | None = None
        self.last_result: SiteTaskResult | None = None
        self.last_native: MapStateArtifact | None = None
        self.last_observation: MapGuardObservation | None = None
        self.error: BaseException | None = None

    def check_owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original Map task worker/thread required")

    def _available(self, operation_id: str) -> None:
        self.check_owner()
        if (
            self.busy
            or self.phase in ("quarantined", "restored", "resumed")
            or operation_id in self.operations
        ):
            raise InvalidTransition(
                "Map task busy, completed, unknown or operation reused"
            )

    def capture_state(
        self, request: SiteTaskRequest, control: OperationControl
    ) -> MapStateArtifact:
        observed = self.guard.require_unchanged(control)
        self.last_observation = observed
        raw = json.dumps(
            dict(
                schema_version="map-complete-guard/1",
                request_sha256=request.digest,
                database=observed.database.decode("utf-8"),
                persistent=observed.persistent.model_dump(mode="json"),
                sha256=observed.sha256,
            ),
            sort_keys=True,
        ).encode()
        native = MapStateArtifact.model_validate(
            self.artifacts.publish(request, raw, observed.sha256, control)
        )
        self.last_native = native
        check_native(native, request)
        spec = self.guard.spec
        if (
            native.file.sha256 != hashlib.sha256(raw).hexdigest()
            or native.file.size_bytes != len(raw)
            or native.state_sha256 != observed.sha256
            or native.plan.token.expected_resource_id != spec.inputs.files.instance_id
            or native.plan.workspace_root != spec.inputs.files.workspace_root
            or self.snapshot is not None
            and (
                native.plan.scope != self.snapshot.native.plan.scope
                or native.plan.token != self.snapshot.native.plan.token
            )
        ):
            raise OwnershipConflict(
                "Native state publication changed original complete bytes or scope"
            )
        return native

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        self.codecs.check_input(request)
        self._available(request.operation.operation_id)
        if request.action == "snapshot":
            if self.phase != "new":
                raise InvalidTransition("Map snapshot already attempted")
        else:
            if self.snapshot is None:
                raise InvalidTransition("Original Map snapshot required")
            ref = snapshot_reference(
                request,
                self.snapshot.request,
                self.snapshot.model_dump_json().encode(),
                self.snapshot_ref,
                schema_version=self.codecs.snapshot_schema,
            )
            allowed = {
                "prepare": ("snapshotted",),
                "inspect": ("prepared",),
                "restore": ("snapshotted", "prepared"),
            }
            if self.phase not in allowed[request.action]:
                raise InvalidTransition("Map task phase does not allow operation")
            if request.action == "restore":
                parent = self.preparation or self.snapshot.request
                if (
                    request.operation.parent_operation_id
                    != parent.operation.operation_id
                ):
                    raise OwnershipConflict(
                        "Map restore changed original preparation parent"
                    )
            self.snapshot_ref = ref
        control.checkpoint()
        self.operations.add(request.operation.operation_id)
        self.busy = True
        self.last_result = self.last_native = None
        try:
            if request.action == "snapshot":
                self.phase = "snapshotting"
                self.snapshot = self.codecs.snapshot(
                    request, self.capture_state(request, control)
                )
                payload = self.snapshot.model_dump_json()
                self.phase = "snapshotted"
            elif request.action == "restore":
                assert self.snapshot is not None
                self.phase = "restoring"
                cleared = self.reset.begin(control)
                payload = self.codecs.restored(
                    request, self.snapshot, cleared
                ).model_dump_json()
                self.phase = "restored"
            else:
                assert self.snapshot is not None
                if request.action == "prepare":
                    self.phase = "preparing"
                    self.preparation = request
                native = self.capture_state(request, control)
                payload = self.codecs.observed(
                    request, self.snapshot, native
                ).model_dump_json()
                self.phase = "prepared"
            result = SiteTaskResult(
                request_sha256=request.digest, private_result=payload
            )
            self.last_result = result
            if request.action == "restore":
                self.restore_request, self.restore_result = request, result
            control.checkpoint()
            return result
        except BaseException as error:
            self.phase, self.error = "quarantined", error
            self.retain_failure(error)
            raise
        finally:
            self.busy = False

    def retain_failure(self, error: BaseException) -> None:
        for name, value in (
            ("map_recovery_snapshot", self.snapshot),
            ("map_native_observation", self.last_observation),
            ("map_native_reference", self.last_native),
            ("map_task_result", self.last_result),
            ("map_frontend_reset_state", self.reset.state),
            ("map_frontend_reset_error", self.reset.error),
        ):
            setattr(error, name, value)

    def capture_task(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteCaptureRequest.model_validate(request)
        if (request.collector_id, request.collector_version) != (
            self.codecs.collector,
            "1",
        ):
            raise ValueError("Unsupported fixed Map complete-state collector")
        result = self.execute_task(request.inspection, control=control)
        return SiteTaskResult(
            request_sha256=request.digest, private_result=result.private_result
        )
