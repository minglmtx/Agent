"""Site lifecycle over an already registered/started fixed process channel.

This client grants no launch right, does not retry, and verifies no whole resource
closure. Retain configuration/last_reply/capture after failure for original-owner
reconciliation; a closed transport is not a closed site resource.
"""

import os
import threading
from typing import Protocol, Literal
from pydantic import TypeAdapter
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
    SiteWorkerReady,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.ports.site_capture import SiteCaptureAuthority
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.site_resume import SiteResumeAuthority
from lab_generate_skill.domain.native_services import NativeServiceExit
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.site_worker import SiteWorkerAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from .worker_protocol import (
    SiteWorkerCommand,
    SiteWorkerReply,
    Phase,
    decode_reply,
    WORKER_MODULE,
)


class SiteWorkerChannel(Protocol):
    @property
    def capture(self) -> CommandCapture: ...
    def exchange(self, payload: bytes, control: OperationControl) -> bytes: ...
    def finish(self, control: OperationControl) -> ProcessTermination: ...
    def abort(self, control: OperationControl) -> ProcessTermination: ...


class SiteWorkerFailure(RuntimeError):
    def __init__(self, reply: SiteWorkerReply) -> None:
        self.reply = reply
        super().__init__("Site worker failed; retain original reply and state")


def fixed_site_argv(configuration: SiteWorkerConfiguration) -> tuple[str, ...]:
    configuration = SiteWorkerConfiguration.model_validate(configuration)
    return (
        configuration.installation.python_executable,
        "-I",
        "-B",
        "-m",
        WORKER_MODULE,
    )


class SupervisedSiteInstance:
    def __init__(
        self,
        channel: SiteWorkerChannel,
        session_id: str,
        configuration: SiteWorkerConfiguration,
        authority: SiteWorkerAuthority,
    ) -> None:
        self.channel, self.authority = channel, authority
        self.configuration = SiteWorkerConfiguration.model_validate(configuration)
        self.session_id = TypeAdapter(Identifier).validate_python(
            session_id, strict=True
        )
        self.controller = current_process_identity()
        self.owner = (os.getpid(), threading.get_ident())
        self.sequence = 0
        self.capture_operations: set[str] = set()
        self.state: Literal[
            "new", "busy", "configured", "ready", "quarantined", "transport_closed"
        ] = "new"
        self.last_reply: SiteWorkerReply | None = None
        self.start_operation: OperationContext | None = None
        self.prepared: SiteWorkerReady | None = None
        self._close_control: OperationControl | None = None

    def _check(
        self,
        phase: Literal["configure", "start", "close"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Site client changed original process/thread")
        self.configuration.check_operation(
            operation, "cleanup" if phase == "close" else "execute"
        )
        if (
            phase == "close"
            and self.start_operation is not None
            and operation.parent_operation_id != self.start_operation.operation_id
        ):
            raise OwnershipConflict("Site cleanup changed original parent operation")
        self.authority.verify(self.configuration, phase, operation, control)

    def _send(
        self,
        phase: Phase,
        operation: OperationContext,
        control: OperationControl,
        task: SiteTaskRequest | None = None,
        resume: SiteResumeRequest | None = None,
        resume_intent_ref: EvidenceRef | None = None,
        resume_authority: SiteResumeAuthority | None = None,
        capture_request: SiteCaptureRequest | None = None,
        capture_intent_ref: EvidenceRef | None = None,
        capture_authority: SiteCaptureAuthority | None = None,
    ) -> SiteWorkerReply:
        if phase == "task":
            if (
                self.owner != (os.getpid(), threading.get_ident())
                or task is None
                or task.operation != operation
            ):
                raise OwnershipConflict("Task changed original client or operation")
            task.check_site(self.configuration)
            self.authority.verify_task(self.configuration, task, control)
        elif phase == "capture":
            if (
                self.owner != (os.getpid(), threading.get_ident())
                or capture_request is None
                or capture_request.operation != operation
                or capture_intent_ref is None
                or capture_authority is None
            ):
                raise OwnershipConflict(
                    "Capture changed original client or required authority"
                )
            capture_request.check_site(self.configuration)
            capture_authority.verify_capture(
                self.configuration, capture_request, capture_intent_ref, control
            )
        elif phase == "resume":
            if (
                self.owner != (os.getpid(), threading.get_ident())
                or resume is None
                or resume.operation != operation
                or resume_intent_ref is None
                or resume_authority is None
            ):
                raise OwnershipConflict(
                    "Resume changed original client or required authority"
                )
            resume.check_site(self.configuration)
            resume_authority.verify_resume(
                self.configuration, resume, resume_intent_ref, control
            )
        else:
            self._check(phase, operation, control)
        if phase == "close":
            control = DeadlineControl(
                min(10, control.checkpoint()), operation.operation_id
            )
            self._close_control = control
        command = SiteWorkerCommand(
            session_id=self.session_id,
            sequence=self.sequence + 1,
            phase=phase,
            operation=operation,
            remaining_seconds=control.checkpoint(),
            controller=self.controller if phase == "configure" else None,
            configuration=self.configuration if phase == "configure" else None,
            task=task,
            capture_request=capture_request,
            capture_intent_ref=capture_intent_ref,
            resume=resume,
            resume_intent_ref=resume_intent_ref,
        )
        if phase == "capture":
            self.capture_operations.add(operation.operation_id)
        self.sequence = command.sequence
        if phase == "configure":
            self.start_operation = operation
        self.state = "busy"
        try:
            raw = self.channel.exchange(command.model_dump_json().encode(), control)
            reply = decode_reply(command, self.configuration, raw)
            self.last_reply = reply
            if reply.error is not None:
                raise SiteWorkerFailure(reply)
            if phase == "configure":
                assert (
                    reply.owner_guard is not None
                    and reply.installed_sources is not None
                )
                self.prepared = SiteWorkerReady(
                    owner_guard=reply.owner_guard,
                    installed_sources=reply.installed_sources,
                )
            control.checkpoint()  # retain actual identity even if cancellation wins
            return reply
        except BaseException as primary:
            self.state = "quarantined"
            try:
                self.channel.abort(DeadlineControl(5, "site-wire-abort"))
            except BaseException as cleanup:
                primary = BaseExceptionGroup(
                    "Site exchange and abort failed", [primary, cleanup]
                )
            setattr(primary, "command_capture", self.channel.capture)
            raise primary

    def configure(
        self, operation: OperationContext, *, control: OperationControl
    ) -> SiteWorkerReady:
        """Return identities before factory/effects; outer owner must pin/persist them."""
        if self.state != "new":
            raise InvalidTransition("Site configure cannot repeat")
        self._send("configure", operation, control)
        assert self.prepared is not None
        self.state = "configured"
        return self.prepared

    def start(
        self, operation: OperationContext, *, control: OperationControl
    ) -> SiteInstanceStarted:
        if self.state != "configured":
            raise InvalidTransition("Site start requires original configured worker")
        if operation != self.start_operation:
            raise OwnershipConflict("Site start changed configured operation")
        reply = self._send("start", operation, control)
        assert reply.started is not None
        self.state = "ready"
        return reply.started

    def execute_task(
        self, request: SiteTaskRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        request = SiteTaskRequest.model_validate(request)
        if self.state != "ready":
            raise InvalidTransition("Task requires original ready site")
        reply = self._send("task", request.operation, control, request)
        assert reply.task_result is not None
        self.state = "ready"
        return reply.task_result

    def close(
        self, operation: OperationContext, *, control: OperationControl
    ) -> tuple[NativeServiceExit, ...] | None:
        if self.state in ("new", "quarantined", "transport_closed"):
            self._check("close", operation, control)
        if self.state == "transport_closed":
            return self.last_reply.exits if self.last_reply else None
        try:
            if self.state in ("new", "quarantined"):
                control = DeadlineControl(
                    min(10, control.checkpoint()), operation.operation_id
                )
                ending = self.channel.abort(control)
                if (
                    ending.state not in ("reaped", "not_started")
                    or ending.cleanup_errors
                ):
                    raise OwnershipConflict("Site abort remains unconfirmed")
            else:
                self._send("close", operation, control)
                assert self._close_control is not None
                control = self._close_control
                ending = self.channel.finish(control)
                if (
                    ending.state != "reaped"
                    or ending.returncode != 0
                    or ending.cleanup_errors
                ):
                    raise OwnershipConflict("Site supervisor did not exit successfully")
            self.state = "transport_closed"
            return self.last_reply.exits if self.last_reply else None
        except BaseException:
            self.state = "quarantined"
            raise

    def resume_frontend(
        self,
        request: SiteResumeRequest,
        intent_ref: EvidenceRef,
        authority: SiteResumeAuthority,
        *,
        control: OperationControl,
    ) -> SiteResumeResult:
        request = SiteResumeRequest.model_validate(request)
        if self.state != "ready":
            raise InvalidTransition("Resume requires original live site")
        reply = self._send(
            "resume",
            request.operation,
            control,
            resume=request,
            resume_intent_ref=intent_ref,
            resume_authority=authority,
        )
        assert reply.resume_result is not None
        self.state = "ready"
        return reply.resume_result

    def capture_task(
        self,
        request: SiteCaptureRequest,
        intent_ref: EvidenceRef,
        authority: SiteCaptureAuthority,
        *,
        control: OperationControl,
    ) -> SiteTaskResult:
        request = SiteCaptureRequest.model_validate(request)
        if (
            self.state != "ready"
            or request.operation.operation_id in self.capture_operations
        ):
            raise InvalidTransition(
                "Capture requires original ready site and unused operation"
            )
        reply = self._send(
            "capture",
            request.operation,
            control,
            capture_request=request,
            capture_intent_ref=intent_ref,
            capture_authority=authority,
        )
        assert reply.capture_result is not None
        self.state = "ready"
        return reply.capture_result
