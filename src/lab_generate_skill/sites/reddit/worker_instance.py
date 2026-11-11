"""Reddit through existing worker Task/Capture/Resume ports, one original site."""

from collections.abc import Callable
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from lab_generate_skill.ports.reddit_native_read_input import RedditNativeReadInputs
from .instance import RedditInstance
from .media_capture import NativeMediaCapture
from .native_reader import RedditNativeReader
from .tasks.image_lifecycle import ImageLifecycle
from .tasks.image_resume import ImageResume


class RedditWorkerInstance:
    def __init__(
        self,
        configuration: SiteWorkerConfiguration,
        instance: RedditInstance,
        artifacts: SitePrivateArtifacts,
        commands: NativeInputCommands,
        inputs: RedditNativeReadInputs,
        username: Callable[[OperationControl], str],
    ) -> None:
        self.configuration = SiteWorkerConfiguration.model_validate(configuration)
        if (
            self.configuration.site_id != "reddit"
            or self.configuration.files != instance.files_plan
            or self.configuration.apptainer != "/usr/bin/apptainer"
        ):
            raise OwnershipConflict("Reddit worker changed original allocated instance")
        self.instance, self.artifacts, self.commands, self.inputs, self.username = (
            instance,
            artifacts,
            commands,
            inputs,
            username,
        )
        self.tasks: ImageLifecycle | None = None
        self.resumption: ImageResume | None = None
        self.started = False
        self.closed = False

    def start(self, control: OperationControl) -> SiteInstanceStarted:
        if self.started or self.closed:
            raise InvalidTransition("Reddit worker startup already attempted or closed")
        control.checkpoint()
        self.started = True
        self.artifacts.initialize(control)
        self.instance.prepare(control)
        endpoint = self.instance.start(control)
        assert self.instance.spec is not None and self.instance.lease is not None
        started = SiteInstanceStarted(
            files=self.instance.files_plan,
            endpoint=endpoint,
            ports=self.instance.lease.ports,
        )
        self.artifacts.bind_instance(started, control)
        self.tasks = ImageLifecycle(
            self.instance,
            RedditNativeReader(
                self.instance.spec,
                self.commands,
                self.inputs,
                NativeMediaCapture(self.instance.spec),
            ),
            self.username,
            self.artifacts,
        )
        return started

    def _task(self) -> ImageLifecycle:
        if self.closed or self.tasks is None:
            raise InvalidTransition("Reddit task requires original open started worker")
        return self.tasks

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        request.check_site(self.configuration)
        return self._task().execute_task(request, control=control)

    def capture_task(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteCaptureRequest.model_validate(request)
        request.check_site(self.configuration)
        return self._task().capture_task(request, control=control)

    def resume_frontend(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult:
        request = SiteResumeRequest.model_validate(request)
        request.check_site(self.configuration)
        task = self._task()
        if self.resumption is not None:
            raise InvalidTransition("Reddit resume already attempted")
        self.resumption = ImageResume(task)
        return self.resumption.resume_frontend(request, control=control)

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self.closed = True
        self.artifacts.stop_new_io()
        return self.instance.stop(control)
