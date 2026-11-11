"""Raw browser session over an already registered, started fixed worker channel.

Mandatory parent authority checks original site/resource permission before each
command. This adapter never launches or retries. Wire failures quarantine and
abort the owned channel; original replies and command capture remain available.
"""

import os
import threading
from collections.abc import Callable
from typing import Protocol
from pydantic import TypeAdapter
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.observation_viewport import ObservationViewport
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.browser_authority import BrowserAuthority
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.browser_capture import BrowserCaptureAuthority
from lab_generate_skill.ports.browser_session import BrowserState
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from .worker_protocol import (
    BrowserWorkerCommand,
    BrowserWorkerReply,
    Phase,
    decode_reply,
    WORKER_MODULE,
)


class BrowserWorkerChannel(Protocol):
    @property
    def capture(self) -> CommandCapture: ...
    def exchange(self, payload: bytes, control: OperationControl) -> bytes: ...
    def finish(self, control: OperationControl) -> ProcessTermination: ...
    def abort(self, control: OperationControl) -> ProcessTermination: ...


class BrowserWorkerFailure(RuntimeError):
    def __init__(self, reply: BrowserWorkerReply) -> None:
        self.reply = reply
        super().__init__("Browser worker failed; preserve reply and original evidence")


def fixed_browser_argv(configuration: BrowserWorkerConfiguration) -> tuple[str, ...]:
    configuration = BrowserWorkerConfiguration.model_validate(configuration)
    return (
        configuration.installation.python_executable,
        "-I",
        "-B",
        "-m",
        WORKER_MODULE,
    )


class SupervisedBrowserSession:
    def __init__(
        self,
        channel: BrowserWorkerChannel,
        session_id: str,
        configuration: BrowserWorkerConfiguration,
        authority: BrowserAuthority,
        *,
        configure_observer: (
            Callable[[BrowserWorkerReply, OperationContext, OperationControl], None]
            | None
        ) = None,
    ) -> None:
        self.channel = channel
        self.session_id = TypeAdapter(Identifier).validate_python(
            session_id, strict=True
        )
        self.configuration = BrowserWorkerConfiguration.model_validate(configuration)
        self.spec = self.configuration.spec
        self.authority = authority
        self.configure_observer = configure_observer
        self.configuration_reply: BrowserWorkerReply | None = None
        self.controller = current_process_identity()
        self.owner = (os.getpid(), threading.get_ident())
        self.state: BrowserState = "new"
        self.last_readout: BrowserReadout | None = None
        self.viewport: ObservationViewport | None = None
        self.last_reply: BrowserWorkerReply | None = None
        self.sequence = 0
        self.transport_failed = False
        self.capture_operations: set[str] = set()
        self.last_capture: BrowserCaptureResult | None = None
        self._close_control: OperationControl | None = None

    def quarantine(self) -> None:
        self.state = "quarantined"

    def _send(
        self,
        phase: Phase,
        operation: OperationContext,
        control: OperationControl,
        action: BrowserAction | None = None,
        capture_request: BrowserCaptureRequest | None = None,
        capture_intent_ref: EvidenceRef | None = None,
        capture_authority: BrowserCaptureAuthority | None = None,
    ) -> BrowserWorkerReply:
        operation = OperationContext.model_validate(operation)
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Browser client changed owner process/thread")
        if (operation.run_id, operation.owner_id, operation.attempt_id) != (
            self.spec.scope.owner.run_id,
            self.spec.scope.owner.owner_id,
            self.spec.scope.attempt_id,
        ):
            raise OwnershipConflict("Browser operation changed scope")
        if self.transport_failed:
            raise InvalidTransition(
                "Failed transport cannot send another browser command"
            )
        if phase == "capture":
            if (
                capture_request is None
                or capture_request.operation != operation
                or capture_intent_ref is None
                or capture_authority is None
                or self.last_readout is None
            ):
                raise OwnershipConflict(
                    "Capture requires original request, observation and authority"
                )
            capture_request.check_readout(self.spec, self.last_readout)
            capture_authority.verify_capture(
                self.configuration, capture_request, capture_intent_ref, control
            )
        elif phase == "configure":
            # Recheck before native start too; configuration does not grant UI
            # admission or create a public observation.
            self.authority.verify(self.spec, "start", None, operation, control)
        else:
            self.authority.verify(self.spec, phase, action, operation, control)
        if phase == "close":
            # Metadata admission is bounded by its caller. Only the physical
            # exchange and reap share this fresh, shorter stop guard.
            control = DeadlineControl(
                min(10, control.checkpoint()), operation.operation_id
            )
            self._close_control = control
        command = BrowserWorkerCommand(
            session_id=self.session_id,
            sequence=self.sequence + 1,
            phase=phase,
            operation=operation,
            remaining_seconds=control.checkpoint(),
            controller=self.controller if phase == "configure" else None,
            configuration=self.configuration if phase == "configure" else None,
            action=action,
            capture_request=capture_request,
            capture_intent_ref=capture_intent_ref,
        )
        if phase == "capture":
            self.capture_operations.add(operation.operation_id)
            self.last_capture = None
        self.sequence = command.sequence
        self.state = "busy"
        try:
            raw = self.channel.exchange(command.model_dump_json().encode(), control)
            reply = decode_reply(command, self.spec, raw)
            self.last_reply = reply
            if reply.captured is not None:
                self.last_capture = reply.captured
            if reply.readout is not None:
                expected_sequence = (
                    0
                    if phase == "start"
                    else (
                        self.last_readout.observation.sequence + 1
                        if self.last_readout is not None
                        else -1
                    )
                )
                if reply.readout.observation.sequence != expected_sequence:
                    raise OwnershipConflict("Browser observation sequence is not next")
                self.last_readout = reply.readout
                self.viewport = reply.viewport
            if reply.error is not None:
                raise BrowserWorkerFailure(reply)
            return reply
        except BaseException as error:
            self.state = "quarantined"
            self.transport_failed = True
            try:
                self.channel.abort(DeadlineControl(5, "browser-wire-abort"))
            except BaseException as cleanup:
                combined = BaseExceptionGroup(
                    "Browser exchange and abort failed", [error, cleanup]
                )
                setattr(combined, "command_capture", self.channel.capture)
                raise combined from None
            setattr(error, "command_capture", self.channel.capture)
            raise

    def start(
        self, operation: OperationContext, *, control: OperationControl
    ) -> BrowserReadout:
        if self.state != "new":
            raise InvalidTransition("Browser start cannot repeat")
        configured = self._send("configure", operation, control)
        self.configuration_reply = configured
        try:
            if self.configure_observer is not None:
                self.configure_observer(configured, operation, control)
            control.checkpoint()
        except BaseException:
            self.state = "quarantined"
            raise
        reply = self._send("start", operation, control)
        assert reply.readout is not None
        self.state = "ready"
        return reply.readout

    def step(
        self,
        action: BrowserAction,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> BrowserReadout:
        if self.state != "ready":
            raise InvalidTransition("Browser is not ready for step")
        reply = self._send(
            "step", operation, control, BrowserAction.model_validate(action)
        )
        assert reply.readout is not None
        result = reply.readout
        self.state = (
            "terminal"
            if result.terminated or result.truncated or result.protocol_terminal
            else "ready"
        )
        return result

    def close(self, operation: OperationContext, *, control: OperationControl) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Browser close changed original owner")
        operation = OperationContext.model_validate(operation)
        if operation.mode != "cleanup":
            raise OwnershipConflict("Browser close requires independent cleanup")
        if (operation.run_id, operation.owner_id, operation.attempt_id) != (
            self.spec.scope.owner.run_id,
            self.spec.scope.owner.owner_id,
            self.spec.scope.attempt_id,
        ):
            raise OwnershipConflict("Browser close changed original scope")
        if self.state == "closed":
            return
        if self.transport_failed or self.sequence == 0:
            self.authority.verify(self.spec, "close", None, operation, control)
            control = DeadlineControl(
                min(10, control.checkpoint()), operation.operation_id
            )
            try:
                termination = self.channel.abort(control)
                if (
                    termination.state not in ("reaped", "not_started")
                    or termination.cleanup_errors
                ):
                    raise OwnershipConflict(
                        "Browser abort termination remains unconfirmed"
                    )
            except BaseException:
                self.state = "quarantined"
                self.transport_failed = True
                raise
        else:
            self._send("close", operation, control)
            assert self._close_control is not None
            control = self._close_control
            try:
                termination = self.channel.finish(control)
                if (
                    termination.state != "reaped"
                    or termination.returncode != 0
                    or termination.cleanup_errors
                ):
                    raise OwnershipConflict(
                        "Browser supervisor did not exit successfully"
                    )
            except BaseException:
                self.state = "quarantined"
                self.transport_failed = True
                raise
        self.state = "closed"

    def capture_page(
        self,
        request: BrowserCaptureRequest,
        intent_ref: EvidenceRef,
        authority: BrowserCaptureAuthority,
        *,
        control: OperationControl,
    ) -> BrowserCaptureResult:
        request = BrowserCaptureRequest.model_validate(request)
        if (
            self.state not in ("ready", "terminal")
            or request.operation.operation_id in self.capture_operations
        ):
            raise InvalidTransition(
                "Capture requires original active browser and unused operation"
            )
        previous = self.state
        reply = self._send(
            "capture",
            request.operation,
            control,
            capture_request=request,
            capture_intent_ref=intent_ref,
            capture_authority=authority,
        )
        assert reply.captured is not None
        self.state = previous
        return reply.captured
