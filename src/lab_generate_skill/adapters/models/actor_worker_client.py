"""Actor engine over an already registered/started worker channel.

This adapter never launches/restarts a process or grants source permission.
The ActorModel adapter owns business intent and once-only execution;
wire sequences only reject duplicate transport commands within one child.
"""

from lab_generate_skill.domain.causal_model import validate_causal_artifact

import os
import threading
from contextlib import contextmanager
from collections.abc import Callable
from collections.abc import Iterator
from typing import Protocol
from pydantic import TypeAdapter
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.release_installation import (
    ReleaseInstallation,
    InstalledReleaseSources,
)
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_engine import (
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    ActorInputBudgetExceeded,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from .actor_worker_protocol import (
    ActorWorkerCommand,
    ActorWorkerReply,
    WorkerOperation,
    decode_reply,
    validate_worker_output,
)


from .actor_worker_exchange import ActorWorkerExchange
from .actor_count_protocol import ActorCountCommand, ActorCountReply, decode_count_reply
from lab_generate_skill.domain.actor_context_count import ActorTokenCount
from .actor_count_exchange import ActorCountExchange


class ActorWorkerChannel(Protocol):
    """An owned channel supporting MAX_WORKER_PACKET and original-child cleanup."""

    @property
    def capture(self) -> CommandCapture: ...
    def exchange(self, payload: bytes, control: OperationControl) -> bytes: ...
    def finish(self, control: OperationControl) -> ProcessTermination: ...
    def abort(self, control: OperationControl) -> ProcessTermination: ...


class ActorWorkerFailure(RuntimeError):
    def __init__(self, reply: ActorWorkerReply | ActorCountReply) -> None:
        self.reply = reply
        super().__init__("Actor worker reported a failure; see structured diagnostic")


class SupervisedActorEngine:
    def __init__(
        self,
        channel: ActorWorkerChannel,
        session_id: str,
        artifact: ReleaseArtifact,
        config: ActorEngineConfig,
        installation: ReleaseInstallation,
    ) -> None:
        self._channel = channel
        self._session = TypeAdapter(Identifier).validate_python(session_id, strict=True)
        self._artifact = validate_causal_artifact(artifact)
        self._config = ActorEngineConfig.model_validate(config)
        self._installation = ReleaseInstallation.model_validate(installation)
        self._installed_sources: InstalledReleaseSources | None = None
        self._controller = current_process_identity()
        self._owner_guard: ProcessOwnerGuard | None = None
        self._configured = False
        self._worker: ProcessIdentity | None = None
        self._closed = False
        self._sequence = 0
        self._pid = os.getpid()
        self._lock = threading.Lock()

    @property
    def session_id(self) -> str:
        """Immutable original route; callers must compare it before sending."""
        return self._session

    @property
    def artifact(self) -> ReleaseArtifact:
        return self._artifact

    @property
    def config(self) -> ActorEngineConfig:
        return self._config

    @property
    def capture(self) -> CommandCapture:
        return self._channel.capture

    @property
    def owner_guard(self) -> ProcessOwnerGuard | None:
        return self._owner_guard

    @property
    def installed_sources(self) -> InstalledReleaseSources | None:
        return self._installed_sources

    @contextmanager
    def _held(
        self, control: OperationControl, *, closing: bool = False
    ) -> Iterator[None]:
        if self._pid != os.getpid():
            raise OwnershipConflict("Worker client cannot cross processes")
        control.checkpoint()
        while not self._lock.acquire(blocking=False):
            control.wait(0.02)
        try:
            control.checkpoint()
            if self._closed and not closing:
                raise OwnershipConflict("Worker client is closed; no automatic restart")
            yield
        finally:
            self._lock.release()

    def _failed(self, error: BaseException) -> None:
        self._closed = True
        try:
            self._channel.abort(DeadlineControl(5, "actor-worker-abort"))
        except BaseException as cleanup:
            combined = BaseExceptionGroup(
                "Actor worker and abort failed", [error, cleanup]
            )
            setattr(combined, "command_capture", self.capture)
            raise combined from None
        setattr(error, "command_capture", self.capture)

    def _exchange(
        self,
        operation: WorkerOperation,
        control: OperationControl,
        request: ActorPrompt | None = None,
        parameters: LocalActorParameters | None = None,
        *,
        prepared_generation: bool = False,
    ) -> ActorWorkerExchange:
        command = ActorWorkerCommand(
            session_id=self._session,
            sequence=self._sequence + 1,
            operation=operation,
            remaining_seconds=control.checkpoint(),
            controller=self._controller if operation == "configure" else None,
            artifact=self._artifact if operation == "configure" else None,
            config=self._config if operation == "configure" else None,
            installation=self._installation if operation == "configure" else None,
            request=request,
            parameters=parameters,
            prepared_generation=(
                "actor-prepared-generation/1" if prepared_generation else None
            ),
        )
        self._sequence = command.sequence
        reply = None
        payload = command.model_dump_json().encode()
        try:
            raw = self._channel.exchange(payload, control)
            reply = decode_reply(command, raw)
            control.checkpoint()
            if reply.status == "error":
                raise ActorWorkerFailure(reply)
            if reply.output is not None:
                assert parameters is not None
                validate_worker_output(reply.output, parameters)
        except BaseException as error:
            if reply is not None:
                setattr(error, "actor_worker_reply", reply)
            self._failed(error)
            raise
        if reply.status == "input_rejected":
            rejected = ActorInputBudgetExceeded(
                "Worker rejected input token budget; no implicit truncation"
            )
            setattr(rejected, "actor_worker_reply", reply)
            raise rejected
        return ActorWorkerExchange(payload, raw)

    def _send(
        self,
        operation: WorkerOperation,
        control: OperationControl,
        request: ActorPrompt | None = None,
        parameters: LocalActorParameters | None = None,
    ) -> ActorWorkerReply:
        return self._exchange(operation, control, request, parameters).decoded_reply

    def _prepare(
        self, request: ActorPrompt, parameters: LocalActorParameters
    ) -> tuple[ActorPrompt, LocalActorParameters]:
        request = ActorPrompt.model_validate(request)
        parameters = LocalActorParameters.model_validate(parameters)
        return request, parameters

    def _configure(self, control: OperationControl) -> None:
        if not self._configured:
            reply = self._send("configure", control)
            assert reply.worker is not None
            self._worker = reply.worker
            assert reply.installed_sources is not None
            self._installed_sources = reply.installed_sources
            self._owner_guard = reply.owner_guard
            self._configured = True

    def configure(self, control: OperationControl) -> ProcessIdentity:
        """Handshake only; no tokenizer/model load, launch or inference permission."""
        with self._held(control):
            self._configure(control)
            assert self._worker is not None
            return self._worker

    def validate(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> None:
        request, parameters = self._prepare(request, parameters)
        with self._held(control):
            self._configure(control)
            self._send("validate", control, request, parameters)

    def measure_exchange(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
        *,
        retention_control: OperationControl | None = None,
    ) -> ActorCountExchange:
        """Read-only exact count on this original worker; no inference or replay."""
        request, parameters = self._prepare(request, parameters)
        with self._held(control):
            self._configure(control)
            command = ActorCountCommand(
                session_id=self._session,
                sequence=self._sequence + 1,
                remaining_seconds=control.checkpoint(),
                request=request,
                parameters=parameters,
            )
            self._sequence = command.sequence
            reply = None
            returned_exchange = None
            try:
                raw = self._channel.exchange(
                    command.model_dump_json().encode(), control
                )
                reply = decode_count_reply(command, raw)
                returned_exchange = ActorCountExchange(
                    command.model_dump_json().encode(), raw
                )
                result_control = (
                    retention_control if retention_control is not None else control
                )
                result_control.checkpoint()
                if reply.status == "error":
                    raise ActorWorkerFailure(reply)
                assert reply.measurement is not None
                reply.measurement.verify(
                    request, parameters, self._artifact, self._config
                )
                result_control.checkpoint()
                return returned_exchange
            except BaseException as error:
                if returned_exchange is not None:
                    setattr(error, "actor_count_exchange", returned_exchange)
                if reply is not None:
                    setattr(error, "actor_worker_reply", reply)
                self._failed(error)
                raise

    def measure(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> ActorTokenCount:
        reply = self.measure_exchange(request, parameters, control).decoded_reply
        assert reply.measurement is not None
        return reply.measurement

    def generate_exchange(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
        *,
        dispatch: Callable[[], OperationControl] | None = None,
    ) -> ActorWorkerExchange:
        """One original exchange, for admitted runtime evidence recording.

        Does not persist, authorize a request, retry, or manufacture an exchange
        from output text. Failed/unknown commands keep existing abort semantics.
        """
        request, parameters = self._prepare(request, parameters)
        with self._held(control):
            self._configure(control)
            actual = control if dispatch is None else dispatch()
            return self._exchange(
                "generate",
                actual,
                request,
                parameters,
                prepared_generation=dispatch is not None,
            )

    def generate(
        self,
        request: ActorPrompt,
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput:
        reply = self.generate_exchange(request, parameters, control).decoded_reply
        assert reply.output is not None
        return reply.output

    def close(self, control: OperationControl) -> None:
        with self._held(control, closing=True):
            if self._closed or not self._configured:
                self._channel.abort(control)
                self._closed = True
                return
            reply = self._send("close", control)
            try:
                self._channel.finish(control)
                control.checkpoint()
            except BaseException as error:
                setattr(error, "actor_worker_reply", reply)
                self._failed(error)
                raise
            self._closed = True
