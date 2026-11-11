"""Shared supervision/receipt rules for fixed installed read-only leaf adapters."""

from collections.abc import Callable
from typing import Protocol, TypeVar
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.errors import EvidenceError, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .commands import ProcessRunner
from .capture import CommandCapture, retained_capture, require_reaped
from .remote_errors import RemoteError


class ReadReply(Protocol):
    @property
    def worker(self) -> ProcessIdentity: ...
    @property
    def error(self) -> RemoteError | None: ...


Reply = TypeVar("Reply", bound=ReadReply)


def run_fixed_read(
    runner: ProcessRunner,
    argv: tuple[str, ...],
    packet: bytes,
    control: OperationControl,
    decode: Callable[[bytes, bytes], Reply],
    check_controller: Callable[[], None],
    failure_factory: Callable[
        [str, CommandCapture | None, Reply | None], EvidenceError
    ],
    interruption_attribute: str,
) -> tuple[Reply, CommandCapture]:
    check_controller()
    capture: CommandCapture | None = None
    reply: Reply | None = None
    phase = "launch"
    try:
        capture = runner.run(argv, control, stdin_bytes=packet)
        phase = "termination"
        ended = require_reaped(capture)
        if (
            capture.complete is not True
            or type(capture.returncode) is not int
            or capture.returncode != 0
            or capture.stderr
            or capture.argv != argv
            or ended.returncode != capture.returncode
        ):
            raise ValueError("Read worker did not complete cleanly")
        phase = "protocol"
        reply = decode(packet, capture.stdout)
        if reply.worker.process_id != ended.process_id:
            raise OwnershipConflict("Read reply is not the reaped child")
        phase = "worker"
        if reply.error is not None:
            raise ValueError("Read worker reported failure")
        phase = "completion"
        check_controller()
        return reply, capture
    except BaseException as error:
        capture = retained_capture(error) or capture
        if reply is None and capture is not None:
            try:
                reply = decode(packet, capture.stdout)
            except Exception:
                pass
        failure = failure_factory(phase, capture, reply)
        if not isinstance(error, Exception):
            setattr(error, interruption_attribute, failure)
            raise
        raise failure from error
