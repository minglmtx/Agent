"""Original SFT client over an already registered/started shared channel.

Never starts a process, grants phase/source rights, retries, or interprets a
direct-child exit as full Slurm/GPU closure. Original ResourceJournal ownership
must be durable before the external caller starts the channel.
"""

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol
from pydantic import TypeAdapter
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.domain.training_worker import TrainingWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from .worker_protocol import (
    TrainingWorkerCommand,
    TrainingWorkerReply,
    Operation,
    decode_reply,
)


class TrainingWorkerChannel(Protocol):
    @property
    def capture(self) -> CommandCapture: ...
    def exchange(self, payload: bytes, control: OperationControl) -> bytes: ...
    def finish(self, control: OperationControl) -> ProcessTermination: ...
    def abort(self, control: OperationControl) -> ProcessTermination: ...


@dataclass(frozen=True)
class TrainingWorkerExchange:
    command: bytes
    reply: bytes

    @property
    def decoded(self) -> TrainingWorkerReply:
        from .worker_protocol import decode_command

        return decode_reply(decode_command(self.command), self.reply)


class TrainingWorkerFailure(RuntimeError):
    def __init__(self, exchange: TrainingWorkerExchange) -> None:
        self.exchange = exchange
        super().__init__(
            "Original SFT worker failed; preserve exact reply, never retry training"
        )


class SupervisedTrainingWorker:
    def __init__(
        self,
        channel: TrainingWorkerChannel,
        session_id: str,
        configuration: TrainingWorkerConfiguration,
    ) -> None:
        self.channel = channel
        self.session_id = TypeAdapter(Identifier).validate_python(
            session_id, strict=True
        )
        self.configuration = TrainingWorkerConfiguration.model_validate(configuration)
        self.controller = current_process_identity()
        self.guard: ProcessOwnerGuard | None = None
        self.installed: InstalledReleaseSources | None = None
        self.state = "new"
        self.sequence = 0
        self.exchanges: list[TrainingWorkerExchange] = []
        self.last_command: bytes | None = None
        self.termination: ProcessTermination | None = None
        self.pid, self.lock = os.getpid(), threading.Lock()

    @contextmanager
    def _held(self, control: OperationControl) -> Iterator[None]:
        if os.getpid() != self.pid:
            raise OwnershipConflict("Training client cannot cross processes")
        control.checkpoint()
        while not self.lock.acquire(blocking=False):
            control.wait(0.02)
        try:
            control.checkpoint()
            yield
        finally:
            self.lock.release()

    def _send(
        self,
        operation: Operation,
        control: OperationControl,
        frozen: TrainingWorkerCommand | None = None,
    ) -> TrainingWorkerReply:
        control.checkpoint()
        command = (
            frozen
            if frozen is not None
            else TrainingWorkerCommand(
                session_id=self.session_id,
                sequence=self.sequence + 1,
                operation=operation,
                remaining_seconds=control.checkpoint(),
                controller=self.controller if operation == "configure" else None,
                configuration=self.configuration if operation == "configure" else None,
                contract_sha256=None,
            )
        )
        self.sequence = command.sequence
        raw = command.model_dump_json().encode()
        # An unanswered command is evidence too; preserve before channel effects.
        self.last_command = raw
        try:
            response = self.channel.exchange(raw, control)
            exchange = TrainingWorkerExchange(raw, response)
            self.exchanges.append(exchange)
            reply = decode_reply(command, response)
            if reply.status != "ok":
                raise TrainingWorkerFailure(exchange)
            control.checkpoint()
            return reply
        except BaseException as error:
            self.state = "failed"
            setattr(error, "training_worker_exchanges", tuple(self.exchanges))
            setattr(error, "training_worker_command", raw)
            try:
                self.termination = self.channel.abort(
                    DeadlineControl(10, "sft-worker-abort")
                )
            except BaseException as cleanup:
                combined = BaseExceptionGroup(
                    "Original SFT worker and abort failed", [error, cleanup]
                )
                setattr(combined, "command_capture", self.channel.capture)
                setattr(combined, "training_worker_command", raw)
                raise combined from None
            setattr(error, "command_capture", self.channel.capture)
            raise

    def configure(self, control: OperationControl) -> TrainingWorkerReply:
        with self._held(control):
            if self.state != "new":
                raise OwnershipConflict("Training configuration is single-use")
            self.state = "configuring"
            reply = self._send("configure", control)
            self.guard, self.installed, self.state = (
                reply.guard,
                reply.installed,
                "configured",
            )
            return reply

    def train(
        self, command: TrainingWorkerCommand, control: OperationControl
    ) -> EvidenceRef:
        command = TrainingWorkerCommand.model_validate(command)
        if (
            command.operation != "train"
            or command.session_id != self.session_id
            or command.sequence != 2
        ):
            raise OwnershipConflict(
                "Training requires its exact frozen original command"
            )
        with self._held(control):
            if self.state != "configured":
                raise OwnershipConflict(
                    "Original training is once-only; failed/unknown never replays"
                )
            self.state = "executing"
            reply = self._send("train", control, command)
            assert reply.execution_ref is not None
            self.state = "returned"
            return reply.execution_ref

    def close(self, control: OperationControl) -> ProcessTermination:
        with self._held(control):
            if self.state == "closed":
                assert self.termination is not None
                return self.termination
            if self.state not in ("configured", "returned"):
                raise OwnershipConflict(
                    "Only original configured worker can close; failed requires explicit abort"
                )
            self.state = "closing"
            self._send("close", control)
            try:
                self.termination = self.channel.finish(control)
                if (
                    self.termination.state != "reaped"
                    or self.termination.returncode != 0
                    or self.termination.cleanup_errors
                ):
                    raise OwnershipConflict(
                        "Original training child clean exit unconfirmed"
                    )
                self.state = "closed"
                return self.termination
            except BaseException as primary:
                self.state = "failed"
                try:
                    self.termination = self.channel.abort(
                        DeadlineControl(10, "sft-finish-abort")
                    )
                except BaseException as cleanup:
                    raise BaseExceptionGroup(
                        "Original SFT finish and abort failed", [primary, cleanup]
                    ) from None
                raise
