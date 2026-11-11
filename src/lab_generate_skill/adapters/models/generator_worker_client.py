"""Generator engine over an already registered/started worker channel.

This adapter never launches/restarts a process or grants source permission.
DurableGeneratorInference still owns business intent and once-only execution;
wire sequences only reject duplicate transport commands within one child.
"""

from lab_generate_skill.domain.causal_model import validate_causal_artifact

import os
import threading
from contextlib import contextmanager
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
from lab_generate_skill.domain.generator_installation import (
    GeneratorInstallation,
    GeneratorInstalledSources,
)
from lab_generate_skill.domain.generator_engine import (
    GeneratorEngineConfig,
)
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorParameters,
    LocalGeneratorOutput,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    GeneratorInputBudgetExceeded,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from .generator_worker_protocol import (
    GeneratorWorkerCommand,
    GeneratorWorkerReply,
    WorkerOperation,
    decode_reply,
    validate_worker_output,
)


from .generator_worker_exchange import GeneratorWorkerExchange


class GeneratorWorkerChannel(Protocol):
    """An owned channel supporting MAX_WORKER_PACKET and original-child cleanup."""

    @property
    def capture(self) -> CommandCapture: ...
    def exchange(self, payload: bytes, control: OperationControl) -> bytes: ...
    def finish(self, control: OperationControl) -> ProcessTermination: ...
    def abort(self, control: OperationControl) -> ProcessTermination: ...


class GeneratorWorkerFailure(RuntimeError):
    def __init__(self, reply: GeneratorWorkerReply) -> None:
        self.reply = reply
        super().__init__(
            "Generator worker reported a failure; see structured diagnostic"
        )


class SupervisedGeneratorEngine:
    def __init__(
        self,
        channel: GeneratorWorkerChannel,
        session_id: str,
        artifact: ReleaseArtifact,
        config: GeneratorEngineConfig,
        installation: GeneratorInstallation,
    ) -> None:
        self._channel = channel
        self._session = TypeAdapter(Identifier).validate_python(session_id, strict=True)
        self._artifact = validate_causal_artifact(artifact)
        self._config = GeneratorEngineConfig.model_validate(config)
        self._installation = GeneratorInstallation.model_validate(installation)
        self._installed_sources: GeneratorInstalledSources | None = None
        self._controller = current_process_identity()
        self._owner_guard: ProcessOwnerGuard | None = None
        self._configured = False
        self._worker: ProcessIdentity | None = None
        self._closed = False
        self._sequence = 0
        self._pid = os.getpid()
        self._lock = threading.Lock()

    @property
    def capture(self) -> CommandCapture:
        return self._channel.capture

    @property
    def owner_guard(self) -> ProcessOwnerGuard | None:
        return self._owner_guard

    @property
    def installed_sources(self) -> GeneratorInstalledSources | None:
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
            self._channel.abort(DeadlineControl(5, "generator-worker-abort"))
        except BaseException as cleanup:
            combined = BaseExceptionGroup(
                "Generator worker and abort failed", [error, cleanup]
            )
            setattr(combined, "command_capture", self.capture)
            raise combined from None
        setattr(error, "command_capture", self.capture)

    def _exchange(
        self,
        operation: WorkerOperation,
        control: OperationControl,
        request: GeneratorModelRequest | None = None,
        parameters: LocalGeneratorParameters | None = None,
    ) -> GeneratorWorkerExchange:
        command = GeneratorWorkerCommand(
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
        )
        self._sequence = command.sequence
        reply = None
        payload = command.model_dump_json().encode()
        try:
            raw = self._channel.exchange(payload, control)
            reply = decode_reply(command, raw)
            control.checkpoint()
            if reply.status == "error":
                raise GeneratorWorkerFailure(reply)
            if reply.output is not None:
                assert parameters is not None
                validate_worker_output(reply.output, parameters)
        except BaseException as error:
            if reply is not None:
                setattr(error, "generator_worker_reply", reply)
            self._failed(error)
            raise
        if reply.status == "input_rejected":
            rejected = GeneratorInputBudgetExceeded(
                "Worker rejected input token budget; no implicit truncation"
            )
            setattr(rejected, "generator_worker_reply", reply)
            raise rejected
        return GeneratorWorkerExchange(payload, raw)

    def _send(
        self,
        operation: WorkerOperation,
        control: OperationControl,
        request: GeneratorModelRequest | None = None,
        parameters: LocalGeneratorParameters | None = None,
    ) -> GeneratorWorkerReply:
        return self._exchange(operation, control, request, parameters).decoded_reply

    def _prepare(
        self, request: GeneratorModelRequest, parameters: LocalGeneratorParameters
    ) -> tuple[GeneratorModelRequest, LocalGeneratorParameters]:
        request = GeneratorModelRequest.model_validate(request)
        parameters = LocalGeneratorParameters.model_validate(parameters)
        if (request.seed, request.temperature) != (
            parameters.seed,
            parameters.temperature,
        ):
            raise OwnershipConflict("Request and worker sampling parameters differ")
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
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        request, parameters = self._prepare(request, parameters)
        with self._held(control):
            self._configure(control)
            self._send("validate", control, request, parameters)

    def generate_exchange(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> GeneratorWorkerExchange:
        """One original exchange, for admitted runtime evidence recording.

        Does not persist, authorize a request, retry, or manufacture an exchange
        from output text. Failed/unknown commands keep existing abort semantics.
        """
        request, parameters = self._prepare(request, parameters)
        with self._held(control):
            self._configure(control)
            return self._exchange("generate", control, request, parameters)

    def generate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput:
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
                setattr(error, "generator_worker_reply", reply)
                self._failed(error)
                raise
            self._closed = True
