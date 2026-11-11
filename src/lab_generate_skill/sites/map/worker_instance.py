"""Selected Map through the original fixed-worker Task/Capture/Resume ports."""

from collections.abc import Callable
import hashlib
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_worker import MapWorkerStorage
from .instance import MapInstance
from .tasks.state_lifecycle import MapTaskLifecycle
from .tasks.state_resume import MapTaskResume
from .tasks.reference_dispatch import MapReferenceDispatch
from .startup_failure import MapHttpStartupFailure


class MapWorkerInstance:
    def __init__(
        self,
        configuration: SiteWorkerConfiguration,
        instance: MapInstance,
        storage: MapWorkerStorage,
        tasks: Callable[[MapInstance, OperationControl], MapTaskLifecycle],
        references: Callable[[MapTaskLifecycle], MapReferenceDispatch] | None = None,
    ) -> None:
        self.configuration = SiteWorkerConfiguration.model_validate(configuration)
        if not callable(getattr(storage, "retain_startup_http", None)):
            raise TypeError("Original startup HTTP failure storage is mandatory")
        inputs = self.configuration.map_inputs
        if (
            self.configuration.site_id != "map"
            or inputs is None
            or inputs.runtime != instance.inputs
        ):
            raise OwnershipConflict(
                "Map worker changed original configured instance inputs"
            )
        expected_port = (
            inputs.origin.requested_web_port
            if isinstance(inputs, MapNavigationWorkerInputs)
            else None
        )
        if instance.expected_web_port != expected_port:
            raise OwnershipConflict(
                "Map assembly ignored the declared original web origin"
            )
        self.instance, self.storage, self.factory = instance, storage, tasks
        self.reference_factory = references
        self.references: MapReferenceDispatch | None = None
        self.started = False
        self.closed = False
        self.start_result: SiteInstanceStarted | None = None
        self.tasks: MapTaskLifecycle | None = None
        self.resumption: MapTaskResume | None = None
        self.error: BaseException | None = None

    def start(self, control: OperationControl) -> SiteInstanceStarted:
        if self.started or self.closed:
            raise InvalidTransition("Map worker startup already attempted or closed")
        control.checkpoint()
        self.started = True
        try:
            self.storage.initialize(control)
            self.instance.prepare(control)
            endpoint = self.instance.start(control)
            assert self.instance.lease is not None
            self.start_result = SiteInstanceStarted(
                files=self.configuration.files,
                endpoint=endpoint,
                ports=self.instance.lease.ports,
            )
            self.storage.bind_instance(self.start_result, control)
            self.tasks = self.factory(self.instance, control)
            inputs = self.configuration.map_inputs
            assert inputs is not None
            if (
                self.instance.spec is None
                or self.tasks.guard.spec != self.instance.spec
                or self.tasks.codecs.task != inputs.scope.task
            ):
                raise OwnershipConflict(
                    "Map task factory changed original native instance"
                )
            if self.reference_factory is not None:
                self.references = self.reference_factory(self.tasks)
                if self.references.lifecycle is not self.tasks:
                    raise OwnershipConflict(
                        "Map reference dispatcher changed original task"
                    )
            control.checkpoint()
            return self.start_result
        except BaseException as error:
            self.error = error
            if isinstance(error, MapHttpStartupFailure):
                try:
                    error.recorded(
                        self.storage.retain_startup_http(error.response, control)
                    )
                except BaseException as diagnostic_error:
                    raise BaseExceptionGroup(
                        "Original Map startup and diagnostic publication failed",
                        [error, diagnostic_error],
                    ) from None
            raise

    def _task(self, request: SiteTaskRequest) -> MapTaskLifecycle:
        request = SiteTaskRequest.model_validate(request)
        request.check_site(self.configuration)
        inputs = self.configuration.map_inputs
        assert inputs is not None
        if (
            request.task != inputs.scope.task
            or request.operation.attempt_id != inputs.scope.attempt_id
            or hashlib.sha256(request.private_input.encode()).hexdigest()
            != inputs.private_input_sha256
        ):
            raise OwnershipConflict(
                "Map task changed frozen source/attempt/private input"
            )
        if self.closed or self.error is not None or self.tasks is None:
            raise InvalidTransition("Map task requires original healthy started worker")
        return self.tasks

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        return self._task(request).execute_task(request, control=control)

    def capture_task(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteCaptureRequest.model_validate(request)
        request.check_site(self.configuration)
        task = self._task(request.inspection)
        if request.collector_id == "map-native-reference":
            if self.references is None:
                raise InvalidTransition("Original Map reference dispatcher unavailable")
            return self.references.capture_task(request, control=control)
        return task.capture_task(request, control=control)

    def resume_frontend(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult:
        request = SiteResumeRequest.model_validate(request)
        request.check_site(self.configuration)
        task = self._task(request.restore_request)
        if self.resumption is not None:
            raise InvalidTransition("Map frontend resume already attempted")
        self.resumption = MapTaskResume(task)
        return self.resumption.resume_frontend(request, control=control)

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self.closed = True
        self.storage.stop_new_io()
        return self.instance.stop(control)
