"""Single original guarded site acquisition; errors close original handles only."""

from collections.abc import Callable
from datetime import datetime, timezone
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.ports.site_capture import SiteCapture
from lab_generate_skill.ports.site_resume import SiteResume
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.ports.site_worker import WorkerSiteInstance
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .worker_diagnostics import native_failure
from .worker_protocol import (
    SiteWorkerCommand,
    SiteWorkerReply,
    decode_reply,
    WORKER_MODULE,
)


class SiteService:
    def __init__(
        self,
        factory: Callable[[SiteWorkerConfiguration], WorkerSiteInstance],
        installation_verifier: Callable[
            [ReleaseInstallation, OperationControl], InstalledReleaseSources
        ],
        guard_verifier: Callable[
            [ProcessIdentity, OperationControl], ProcessOwnerGuard
        ],
    ) -> None:
        self.factory, self.installation_verifier, self.guard_verifier = (
            factory,
            installation_verifier,
            guard_verifier,
        )
        self.instance: WorkerSiteInstance | None = None
        self.configuration: SiteWorkerConfiguration | None = None
        self.owner_guard: ProcessOwnerGuard | None = None
        self.first: SiteWorkerCommand | None = None
        self.sequence = 0
        self.closed = False
        self.exits: tuple[NativeServiceExit, ...] | None = None
        self.stop_attempted = False
        self.task_operations: set[str] = set()

    def close(self, control: OperationControl | None = None) -> None:
        self.closed = True
        if self.instance is None:
            self.exits = ()
        if self.instance is not None and not self.stop_attempted:
            self.stop_attempted = True
            try:
                self.exits = self.instance.stop(
                    control
                    if control is not None
                    else DeadlineControl(20, "site-final-stop")
                )
            except BaseException as error:
                observed = getattr(error, "service_exits", None)
                if isinstance(observed, tuple) and all(
                    isinstance(f, NativeServiceExit) for f in observed
                ):
                    self.exits = observed
                raise
            if any(f.state != "reaped" for f in self.exits):
                raise OwnershipConflict("Original site launchers remain unconfirmed")

    def handle(self, command: SiteWorkerCommand) -> SiteWorkerReply:
        command = SiteWorkerCommand.model_validate(command)
        started = None
        task_result = None
        resume_result = None
        capture_result = None
        owner_guard = None
        installed = None
        error = None
        try:
            if self.closed or command.sequence != self.sequence + 1:
                raise OwnershipConflict(
                    "Site command is not the next original sequence"
                )
            self.sequence = command.sequence
            seconds = min(
                command.remaining_seconds,
                (
                    command.operation.deadline - datetime.now(timezone.utc)
                ).total_seconds(),
            )
            control = DeadlineControl(seconds, command.operation.operation_id)
            if command.phase == "configure":
                assert (
                    command.controller is not None and command.configuration is not None
                )
                self.first, self.configuration = command, command.configuration
                guard = self.guard_verifier(command.controller, control)
                if guard.controller != command.controller:
                    raise OwnershipConflict("Site guard changed original controller")
                actual = self.installation_verifier(
                    self.configuration.installation, control
                )
                expected = self.configuration.installation
                if (actual.release_id, actual.manifest_sha256, actual.executable) != (
                    expected.manifest.release_id,
                    expected.manifest_ref.sha256,
                    expected.python_executable,
                ) or WORKER_MODULE not in {m.name for m in actual.modules}:
                    raise OwnershipConflict(
                        "Site installation differs from original declaration"
                    )
                owner_guard, installed, self.owner_guard = guard, actual, guard
                control.checkpoint()
            else:
                if (
                    self.first is None
                    or self.configuration is None
                    or self.owner_guard is None
                ):
                    raise OwnershipConflict("Site was never configured")
                mode = "cleanup" if command.phase == "close" else "execute"
                if command.phase == "task":
                    assert command.task is not None
                    command.task.check_site(self.configuration)
                elif command.phase == "capture":
                    assert command.capture_request is not None
                    command.capture_request.check_site(self.configuration)
                elif command.phase == "resume":
                    assert command.resume is not None
                    command.resume.check_site(self.configuration)
                else:
                    self.configuration.check_operation(command.operation, mode)
                if command.session_id != self.first.session_id:
                    raise OwnershipConflict("Site command changed original session")
                if (
                    command.phase == "start"
                    and command.operation != self.first.operation
                ):
                    raise OwnershipConflict(
                        "Site start changed original configured operation"
                    )
                if (
                    command.phase == "close"
                    and command.operation.parent_operation_id
                    != self.first.operation.operation_id
                ):
                    raise OwnershipConflict("Site cleanup changed original parent")
                assert self.first.controller is not None
                if (
                    self.guard_verifier(self.first.controller, control)
                    != self.owner_guard
                ):
                    raise OwnershipConflict("Original site guard changed")
                if command.phase == "start":
                    control.checkpoint()
                    self.instance = self.factory(self.configuration)
                    started = self.instance.start(control)
                    if started.files != self.configuration.files:
                        raise OwnershipConflict("Site instance changed original plan")
                elif command.phase == "task":
                    assert command.task is not None
                    if (
                        self.instance is None
                        or command.operation.operation_id in self.task_operations
                    ):
                        raise OwnershipConflict(
                            "Task requires started instance and unused operation"
                        )
                    self.task_operations.add(command.operation.operation_id)
                    returned = SiteTaskResult.model_validate(
                        self.instance.execute_task(command.task, control=control)
                    )
                    if returned.request_sha256 != command.task.digest:
                        raise OwnershipConflict("Task result changed original request")
                    task_result = returned
                    control.checkpoint()
                elif command.phase == "capture":
                    assert command.capture_request is not None
                    if (
                        not isinstance(self.instance, SiteCapture)
                        or command.operation.operation_id in self.task_operations
                    ):
                        raise OwnershipConflict(
                            "Capture requires original supported instance and unused operation"
                        )
                    self.task_operations.add(command.operation.operation_id)
                    captured = SiteTaskResult.model_validate(
                        self.instance.capture_task(
                            command.capture_request, control=control
                        )
                    )
                    if captured.request_sha256 != command.capture_request.digest:
                        raise OwnershipConflict(
                            "Capture result changed original request"
                        )
                    capture_result = captured
                    control.checkpoint()
                elif command.phase == "resume":
                    assert command.resume is not None
                    if (
                        not isinstance(self.instance, SiteResume)
                        or command.operation.operation_id in self.task_operations
                    ):
                        raise OwnershipConflict(
                            "Resume requires original supported instance and unused operation"
                        )
                    self.task_operations.add(command.operation.operation_id)
                    resumed = SiteResumeResult.model_validate(
                        self.instance.resume_frontend(command.resume, control=control)
                    )
                    if resumed.request_sha256 != command.resume.digest:
                        raise OwnershipConflict(
                            "Resume result changed original request"
                        )
                    resume_result = resumed
                    control.checkpoint()
                else:
                    self.close(control)
        except BaseException as primary:
            native_failure(primary)
            try:
                self.close()
            except BaseException as cleanup:
                primary = BaseExceptionGroup(
                    "Site command and original cleanup failed", [primary, cleanup]
                )
            error = describe_error(primary)
        reply = SiteWorkerReply(
            session_id=command.session_id,
            sequence=command.sequence,
            phase=command.phase,
            command_sha256=command.digest,
            error=error,
            started=started,
            task_result=task_result,
            resume_result=resume_result,
            capture_result=capture_result,
            exits=self.exits,
            owner_guard=owner_guard,
            installed_sources=installed,
        )
        if self.configuration is not None:
            decode_reply(command, self.configuration, reply.model_dump_json().encode())
        return reply
