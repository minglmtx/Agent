"""Selected GitLab lifecycle through existing Task/Capture/Resume worker ports."""

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
from lab_generate_skill.domain.native_private_json import (
    GITLAB_PRIVATE_JSON,
    GITLAB_GROUP_PRIVATE_JSON,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_input_commands import NativeInputCommands
from lab_generate_skill.ports.site_evidence import SitePrivateArtifacts
from .instance import GitlabInstance
from .ssh_native_reader import GitlabSshNativeReader
from .tasks.ssh_key_lifecycle import SshKeyLifecycle
from .tasks.ssh_key_resume import SshKeyResume
from .tasks.group_lifecycle import GroupLifecycle
from .tasks.group_resume import GroupResume
from .tasks.group_worker_inputs import verify_group_worker_inputs


class GitlabWorkerInstance:
    def __init__(
        self,
        configuration: SiteWorkerConfiguration,
        instance: GitlabInstance,
        artifacts: SitePrivateArtifacts,
        commands: NativeInputCommands,
        username: Callable[[OperationControl], str],
        *,
        group_lifecycle_factory: Callable[
            [
                GitlabInstance,
                NativeInputCommands,
                Callable[[OperationControl], str],
                SitePrivateArtifacts,
            ],
            GroupLifecycle,
        ],
    ) -> None:
        self.configuration = SiteWorkerConfiguration.model_validate(configuration)
        if (
            self.configuration.site_id != "gitlab"
            or self.configuration.files != instance.files_plan
        ):
            raise OwnershipConflict("GitLab worker changed original allocated instance")
        assert self.configuration.private_evidence is not None
        if self.configuration.private_evidence.profile not in (
            GITLAB_PRIVATE_JSON,
            GITLAB_GROUP_PRIVATE_JSON,
        ):
            raise ValueError(
                "GitLab task lifecycle is not registered for this declared profile"
            )
        self.instance, self.artifacts, self.commands, self.username = (
            instance,
            artifacts,
            commands,
            username,
        )
        self.group_lifecycle_factory = group_lifecycle_factory
        self.tasks: SshKeyLifecycle | GroupLifecycle | None = None
        self.resumption: SshKeyResume | GroupResume | None = None
        self.started = False
        self.closed = False

    def start(self, control: OperationControl) -> SiteInstanceStarted:
        if self.started or self.closed:
            raise InvalidTransition("GitLab worker startup already attempted or closed")
        self.started = True
        self.artifacts.initialize(control)
        self.instance.prepare(control)
        endpoint = self.instance.start(control)
        declared = self.configuration.gitlab_group_inputs
        if declared is not None and endpoint != declared.origin.endpoint:
            raise OwnershipConflict("Group startup changed original declared endpoint")
        assert self.instance.spec is not None and self.instance.lease is not None
        started = SiteInstanceStarted(
            files=self.instance.files_plan,
            endpoint=endpoint,
            ports=self.instance.lease.ports,
        )
        self.artifacts.bind_instance(started, control)
        assert self.configuration.private_evidence is not None
        if self.configuration.private_evidence.profile == GITLAB_PRIVATE_JSON:
            self.tasks = SshKeyLifecycle(
                self.instance,
                GitlabSshNativeReader(self.instance.spec, self.commands),
                self.username,
                self.artifacts,
            )
        else:
            self.tasks = self.group_lifecycle_factory(
                self.instance,
                self.commands,
                self.username,
                self.artifacts,
            )
        return started

    def _family(self, request: SiteTaskRequest) -> None:
        assert self.configuration.private_evidence is not None
        if request.task.family != self.configuration.private_evidence.profile.family:
            raise OwnershipConflict("GitLab task changed original declared family")
        verify_group_worker_inputs(self.configuration, request)

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        request.check_site(self.configuration)
        self._family(request)
        if self.tasks is None:
            raise InvalidTransition("GitLab task requires original started worker")
        return self.tasks.execute_task(request, control=control)

    def capture_task(
        self, request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteCaptureRequest.model_validate(request)
        request.check_site(self.configuration)
        self._family(request.inspection)
        if self.tasks is None:
            raise InvalidTransition("GitLab capture requires original task lifecycle")
        return self.tasks.capture_task(request, control=control)

    def resume_frontend(
        self, request: SiteResumeRequest, *, control: OperationControl
    ) -> SiteResumeResult:
        request = SiteResumeRequest.model_validate(request)
        request.check_site(self.configuration)
        self._family(request.restore_request)
        if self.tasks is None or self.resumption is not None:
            raise InvalidTransition("GitLab resume requires original task and one call")
        self.resumption = (
            SshKeyResume(self.tasks)
            if isinstance(self.tasks, SshKeyLifecycle)
            else GroupResume(self.tasks)
        )
        return self.resumption.resume_frontend(request, control=control)

    def stop(self, control: OperationControl) -> tuple[NativeServiceExit, ...]:
        self.closed = True
        self.artifacts.stop_new_io()
        return self.instance.stop(control)
