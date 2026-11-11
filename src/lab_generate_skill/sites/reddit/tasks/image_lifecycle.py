"""Selected native image task inside the original worker, without outer authority.

The registered task authority persists intent and proves browser closure before
restore. This leaf retains every attempted operation and never retries unknowns.
"""

from collections.abc import Callable
import os
import threading
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.reddit_native_read_input import BaselineIdsRef
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from ..instance import RedditInstance
from ..native_reader import RedditNativeReader
from ..native_schema import NativeCapture
from ..image_state import ImageReference
from .image_spec import NativeImageSpec
from .image_admission import task_input, snapshot_reference
from .image_recovery import (
    ImageRecoverySnapshot,
    ImageObserved,
    ImageRestored,
    native_result,
)


class ImageLifecycle:
    def __init__(
        self,
        instance: RedditInstance,
        reader: RedditNativeReader,
        username: Callable[[OperationControl], str],
        artifacts: SitePrivateArtifacts,
    ) -> None:
        self.instance, self.reader, self.username, self.artifacts = (
            instance,
            reader,
            username,
            artifacts,
        )
        self.owner = os.getpid(), threading.get_ident()
        self.phase = "new"
        self.busy = False
        self.operations: set[str] = set()
        self.snapshot: ImageRecoverySnapshot | None = None
        self.snapshot_ref: EvidenceRef | None = None
        self.native_before: ImageReference | None = None
        self.baseline_ids: BaselineIdsRef | None = None
        self.preparation: SiteTaskRequest | None = None
        self.restore_request: SiteTaskRequest | None = None
        self.restore_result: SiteTaskResult | None = None
        self.last_result: SiteTaskResult | None = None
        self.last_native: SitePrivateEvidenceResult | None = None

    def check_owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Reddit task requires original worker/thread")

    def _available(self, operation_id: str) -> None:
        self.check_owner()
        if (
            self.busy
            or self.phase in ("quarantined", "restored", "resumed")
            or operation_id in self.operations
        ):
            raise InvalidTransition(
                "Reddit task busy, completed, unknown or operation reused"
            )

    def _original(self, request: SiteTaskRequest) -> None:
        if self.snapshot is None:
            raise InvalidTransition("Original Reddit snapshot required")
        self.snapshot_ref = snapshot_reference(
            request,
            self.snapshot.request,
            self.snapshot.model_dump_json().encode(),
            self.snapshot.schema_version,
            self.snapshot_ref,
        )
        if request.action == "restore":
            parent = self.preparation or self.snapshot.request
            if request.operation.parent_operation_id != parent.operation.operation_id:
                raise OwnershipConflict(
                    "Reddit restore changed original preparation parent"
                )

    def _publish(
        self,
        request: SiteTaskRequest,
        value: ImageReference | NativeCapture,
        control: OperationControl,
    ) -> SitePrivateEvidenceResult:
        result = self.artifacts.publish(
            request, value.model_dump_json().encode(), control=control
        )
        native_result(result, request)
        self.last_native = result
        return result

    def capture_native(
        self, request: SiteTaskRequest, spec: NativeImageSpec, control: OperationControl
    ) -> tuple[NativeCapture, SitePrivateEvidenceResult]:
        if self.baseline_ids is None or self.native_before is None:
            raise InvalidTransition("Complete original native baseline required")
        measured = self.reader.capture(
            spec, self.native_before.account.username, self.baseline_ids, control
        )
        return measured, self._publish(request, measured, control)

    def require_pristine(self, measured: NativeCapture) -> None:
        # SQL projection already implements exactly the original users.last_seen
        # exception. No new exception or allowed image mutation during preparation.
        if self.native_before is None or measured != self.native_before.capture:
            raise OwnershipConflict("Complete original Reddit native baseline differs")

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        spec = task_input(request)
        self._available(request.operation.operation_id)
        if request.action == "snapshot":
            if self.phase != "new":
                raise InvalidTransition("Reddit snapshot already attempted")
        else:
            self._original(request)
            allowed = {
                "prepare": ("snapshotted",),
                "inspect": ("prepared",),
                "restore": ("snapshotted", "prepared"),
            }
            if self.phase not in allowed[request.action]:
                raise InvalidTransition("Reddit task phase does not allow operation")
        control.checkpoint()
        self.operations.add(request.operation.operation_id)
        self.busy = True
        self.last_result = None
        self.last_native = None
        try:
            if request.action == "snapshot":
                self.phase = "snapshotting"
                initialization = self.instance.media_initialization
                if initialization is None:
                    raise InvalidTransition(
                        "Native storage preparation evidence required before baseline"
                    )
                self.native_before = self.reader.reference(
                    spec, self.username(control), control
                )
                initialization.check_baseline(self.native_before.capture.native_media)
                before = self._publish(request, self.native_before, control)
                self.baseline_ids = self.reader.inputs.publish(
                    request,
                    self.native_before.known_id_ranges,
                    self.native_before.capture.complete13.submissions.count,
                    control,
                )
                state = self.instance.snapshot_and_restart(control)
                self.snapshot = ImageRecoverySnapshot(
                    request=request,
                    state=state,
                    native_before=before,
                    media_initialization=initialization,
                    baseline_ids=self.baseline_ids,
                )
                payload = self.snapshot.model_dump_json()
                self.phase = "snapshotted"
            elif request.action == "restore":
                assert self.snapshot is not None
                self.phase = "restoring"
                inventory = self.instance.restore(self.snapshot.state, control)
                stopped = self.instance.generations[-1].quiescence
                assert stopped is not None
                payload = ImageRestored(
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
                measured, ref = self.capture_native(request, spec, control)
                assert self.snapshot is not None
                if request.action == "prepare":
                    self.require_pristine(measured)
                payload = ImageObserved(
                    request=request, snapshot=self.snapshot, native=ref
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
            self.phase = "quarantined"
            self.retain_failure(error)
            raise
        finally:
            self.busy = False

    def retain_failure(self, error: BaseException) -> None:
        for name, value in (
            ("reddit_recovery_snapshot", self.snapshot),
            ("reddit_physical_snapshot", self.instance.snapshot),
            ("reddit_restored_inventory", self.instance.restored),
            ("reddit_baseline_ids", self.baseline_ids),
            ("reddit_native_database", self.reader.last_database),
            ("reddit_native_result", self.reader.last_result),
            ("reddit_native_reference", self.last_native),
            ("reddit_task_result", self.last_result),
        ):
            setattr(error, name, value)

    def capture_task(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteCaptureRequest.model_validate(request)
        if (request.collector_id, request.collector_version) != (
            "reddit-native-image",
            "1",
        ):
            raise ValueError("Unsupported fixed Reddit native collector")
        result = self.execute_task(request.inspection, control=control)
        return SiteTaskResult(
            request_sha256=request.digest, private_result=result.private_result
        )
