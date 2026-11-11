"""One original GitLab task operation engine, with fixed family adapters.

Only trusted Python assembly supplies the typed readers/factories. No request
selects code. Concrete family contracts remain the only public wire boundary.
"""

from collections.abc import Callable
import os
import threading
from typing import Generic, Protocol, TypeVar
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from ..instance import GitlabInstance
from ..services import GitlabGeneration
from ..snapshot import GitlabSnapshot, GitlabInventory
from .native_snapshot import same_native_snapshot

Spec = TypeVar("Spec")
State = TypeVar("State")
SpecIn = TypeVar("SpecIn", contravariant=True)
StateOut = TypeVar("StateOut", covariant=True)


class NativeReader(Protocol[SpecIn, StateOut]):
    @property
    def captured_raw(self) -> bytes | None: ...
    def capture(
        self, spec: SpecIn, username: str, control: OperationControl
    ) -> StateOut: ...


class TaskSnapshot(Protocol):
    @property
    def request(self) -> SiteTaskRequest: ...
    @property
    def state(self) -> GitlabSnapshot: ...
    @property
    def schema_version(self) -> str: ...
    def model_dump_json(self) -> str: ...


Snapshot = TypeVar("Snapshot", bound=TaskSnapshot)


class GitlabNativeLifecycle(Generic[Spec, State, Snapshot]):
    def __init__(
        self,
        instance: GitlabInstance,
        reader: NativeReader[Spec, State],
        username: Callable[[OperationControl], str],
        artifacts: SitePrivateArtifacts,
        *,
        label: str,
        collector: str,
        inputs: Callable[[SiteTaskRequest], Spec],
        same_state: Callable[[State, State], bool],
        validate_baseline: Callable[[Spec, State], None],
        snapshot: Callable[
            [SiteTaskRequest, GitlabSnapshot, SitePrivateEvidenceResult], Snapshot
        ],
        observed: Callable[[SiteTaskRequest, Snapshot, SitePrivateEvidenceResult], str],
        restored: Callable[
            [
                SiteTaskRequest,
                Snapshot,
                GitlabGeneration,
                GitlabInventory,
                SitePrivateEvidenceResult,
            ],
            str,
        ],
    ) -> None:
        self.instance, self.reader, self.username, self.artifacts = (
            instance,
            reader,
            username,
            artifacts,
        )
        self.label, self.collector = label, collector
        self.inputs, self.same_state, self.validate_baseline = (
            inputs,
            same_state,
            validate_baseline,
        )
        self.make_snapshot, self.make_observed, self.make_restored = (
            snapshot,
            observed,
            restored,
        )
        self.owner = (os.getpid(), threading.get_ident())
        self.phase, self.busy = "new", False
        self.operations: set[str] = set()
        self.snapshot: Snapshot | None = None
        self.snapshot_ref: EvidenceRef | None = None
        self.native_before: State | None = None
        self.last_native_result: SitePrivateEvidenceResult | None = None
        self.preparation: SiteTaskRequest | None = None
        self.restore_request: SiteTaskRequest | None = None
        self.restore_result: SiteTaskResult | None = None
        self.resume_attempted = False

    def check_owner(self) -> None:
        if (os.getpid(), threading.get_ident()) != self.owner:
            raise OwnershipConflict(
                self.label + " task changed original process/thread"
            )

    def _available(self, operation_id: str) -> None:
        self.check_owner()
        if (
            self.busy
            or self.phase in ("quarantined", "restored")
            or operation_id in self.operations
        ):
            raise InvalidTransition(
                self.label + " task busy, completed, unknown or operation reused"
            )

    def _original(self, request: SiteTaskRequest) -> None:
        if self.snapshot is None:
            raise InvalidTransition("Original " + self.label + " snapshot required")
        self.snapshot_ref = same_native_snapshot(
            request,
            self.snapshot.request,
            self.snapshot.model_dump_json().encode(),
            self.snapshot.schema_version,
            self.snapshot_ref,
            self.label,
        )
        if request.action == "restore":
            parent = self.preparation or self.snapshot.request
            if request.operation.parent_operation_id != parent.operation.operation_id:
                raise OwnershipConflict(
                    self.label + " restore changed original preparation parent"
                )

    def capture_native(
        self, request: SiteTaskRequest, spec: Spec, control: OperationControl
    ) -> tuple[State, SitePrivateEvidenceResult]:
        self.check_owner()
        observed = self.reader.capture(spec, self.username(control), control)
        raw = self.reader.captured_raw
        if raw is None:
            raise RuntimeError("Native capture did not retain original complete bytes")
        result = self.artifacts.publish(request, raw, control=control)
        self.last_native_result = result
        return observed, result

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        spec = self.inputs(request)
        self._available(request.operation.operation_id)
        if request.action == "snapshot":
            if self.phase != "new":
                raise InvalidTransition(self.label + " snapshot already attempted")
        else:
            self._original(request)
            expected = {
                "prepare": ("snapshotted",),
                "inspect": ("prepared",),
                "restore": ("snapshotted", "prepared"),
            }
            if self.phase not in expected[request.action]:
                raise InvalidTransition(
                    self.label + " task phase does not allow operation"
                )
        control.checkpoint()
        self.operations.add(request.operation.operation_id)
        self.busy = True
        try:
            if request.action == "snapshot":
                self.phase = "snapshotting"
                self.native_before, before = self.capture_native(request, spec, control)
                self.validate_baseline(spec, self.native_before)
                state = self.instance.snapshot_and_restart(control)
                self.snapshot = self.make_snapshot(request, state, before)
                payload = self.snapshot.model_dump_json()
                self.phase = "snapshotted"
            elif request.action == "restore":
                assert self.snapshot is not None and self.native_before is not None
                self.phase = "restoring"
                inventory = self.instance.restore(self.snapshot.state, control)
                assert self.instance.generations[-2].quiescence is not None
                measured, native = self.capture_native(request, spec, control)
                if not self.same_state(self.native_before, measured):
                    raise OwnershipConflict(
                        "Complete native " + self.label + " state was not restored"
                    )
                payload = self.make_restored(
                    request,
                    self.snapshot,
                    self.instance.generations[-2],
                    inventory,
                    native,
                )
                self.phase = "restored"
            else:
                if request.action == "prepare":
                    self.phase, self.preparation = "preparing", request
                measured, native = self.capture_native(request, spec, control)
                assert self.snapshot is not None and self.native_before is not None
                if request.action == "prepare" and not self.same_state(
                    self.native_before, measured
                ):
                    raise OwnershipConflict(
                        "Read-only "
                        + self.label
                        + " preparation changed complete initial state"
                    )
                payload = self.make_observed(request, self.snapshot, native)
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
            setattr(error, "gitlab_recovery_snapshot", self.snapshot)
            setattr(error, "gitlab_restored_inventory", self.instance.restored)
            setattr(error, "gitlab_last_native_result", self.last_native_result)
            raise
        finally:
            self.busy = False

    def capture_task(
        self, capture: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        capture = SiteCaptureRequest.model_validate(capture)
        if (capture.collector_id, capture.collector_version) != (self.collector, "1"):
            raise ValueError("Unsupported fixed GitLab native collector")
        returned = self.execute_task(capture.inspection, control=control)
        return SiteTaskResult(
            request_sha256=capture.digest, private_result=returned.private_result
        )
