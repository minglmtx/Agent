"""Reusable process transport, not model admission or persistent ownership.

The owner MUST register launch intent before start. This primitive never retries
start/exchange or proves escaped descendants, supervisor-death containment or a
hard bound for Popen/cancellation-provider I/O. A failed session cannot reopen.
Each exchange returns one bounded raw frame; the role protocol must bind identity
and sequence. All closes use existing direct-child termination observations.
"""

import os
import re
import threading
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from collections.abc import Iterator
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .capture import CommandCapture, ProcessTermination
from .cleanup import finish_process
from .framing import frame
from .session_io import exchange, wait_exit, drain_pending_error


class FramedProcessSession:
    def __init__(
        self,
        argv: tuple[str, ...],
        *,
        max_frame_bytes: int = 8 * 1024 * 1024,
        max_stderr_bytes: int = 1024 * 1024,
        reap_timeout: float = 2.0,
        cuda_visible_devices: str | None = None,
    ) -> None:
        if (
            type(argv) is not tuple
            or not argv
            or any(type(a) is not str or not a or "\0" in a for a in argv)
            or not os.path.isabs(argv[0])
        ):
            raise ValueError(
                "Session needs trusted absolute executable and exact argv tuple"
            )
        if any(
            type(x) is not int or not 1 <= x <= 64 * 1024 * 1024
            for x in (max_frame_bytes, max_stderr_bytes)
        ):
            raise ValueError(
                "Session byte limits must be integers between 1 and 64 MiB"
            )
        if type(reap_timeout) not in (int, float) or not 0 < reap_timeout <= 10:
            raise ValueError("Independent reap timeout must be finite and in (0,10]")
        if cuda_visible_devices is not None and (
            type(cuda_visible_devices) is not str
            or not re.fullmatch(
                r"(?:[0-9]+(?:,[0-9]+)*|GPU-[0-9a-fA-F-]{36})", cuda_visible_devices
            )
        ):
            raise ValueError(
                "Only explicit numeric or GPU UUID device selection is accepted"
            )
        self._argv = argv
        self._limit, self._stderr_limit, self._reap_timeout = (
            max_frame_bytes,
            max_stderr_bytes,
            float(reap_timeout),
        )
        self._cuda = cuda_visible_devices
        self._process: subprocess.Popen[bytes] | None = None
        self._state = "new"
        self._pid = os.getpid()
        self._lock = threading.Lock()
        self._reply = bytearray()
        self._stderr = bytearray()
        self._termination: ProcessTermination | None = None

    @property
    def process_id(self) -> int | None:
        """Original Popen identity, without polling/reaping or granting authority."""
        return None if self._process is None else self._process.pid

    @property
    def capture(self) -> CommandCapture:
        return CommandCapture(
            self._argv,
            None if self._process is None else self._process.returncode,
            bytes(self._reply),
            bytes(self._stderr),
            self._state == "finished",
            self._termination,
        )

    @contextmanager
    def _held(self, control: OperationControl) -> Iterator[None]:
        if os.getpid() != self._pid:
            raise OwnershipConflict("Session cannot cross process boundaries")
        control.checkpoint()
        while not self._lock.acquire(blocking=False):
            control.wait(0.02)
        try:
            control.checkpoint()
            yield
        finally:
            self._lock.release()

    def _end(
        self, primary: BaseException | None, *, succeeded: bool = False
    ) -> ProcessTermination:
        errors: list[BaseException] = []
        self._state = "failed"
        if self._process is None:
            self._termination = ProcessTermination(None, "not_started", None, False)
        else:
            try:
                drain_pending_error(self._process, self._stderr, self._stderr_limit)
            except BaseException as error:
                errors.append(error)
            previous = self._termination
            # Shared cleanup owns the no-signal-after-reap rule; retain the
            # original kill observation when only stream cleanup is retried.
            self._termination, closing = finish_process(
                self._process,
                succeeded=succeeded,
                reap_timeout=self._reap_timeout,
            )
            if previous is not None and previous.kill_requested:
                self._termination = replace(self._termination, kill_requested=True)
            errors.extend(closing)
        if errors and self._termination is not None:
            self._termination = replace(
                self._termination,
                cleanup_errors=tuple(type(error).__name__ for error in errors),
            )
        if succeeded and not errors:
            self._state = "finished"
        if errors:
            combined = BaseExceptionGroup(
                "Session operation and cleanup failed",
                ([primary] if primary else []) + errors,
            )
            setattr(combined, "command_capture", self.capture)
            raise combined from None
        if primary is not None:
            setattr(primary, "command_capture", self.capture)
        assert self._termination is not None
        return self._termination

    def start(self, control: OperationControl) -> None:
        with self._held(control):
            if self._state != "new":
                raise OwnershipConflict(
                    "Session start is single-use; no implicit restart"
                )
            self._state = "starting"
            environment = {
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "TZ": "UTC",
            }
            if self._cuda is not None:
                environment["CUDA_VISIBLE_DEVICES"] = self._cuda
            try:
                self._process = subprocess.Popen(
                    self._argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    start_new_session=True,
                    close_fds=True,
                    env=environment,
                )
                for stream in (
                    self._process.stdin,
                    self._process.stdout,
                    self._process.stderr,
                ):
                    assert stream is not None
                    os.set_blocking(stream.fileno(), False)
                control.checkpoint()
                self._state = "running"
            except BaseException as error:
                self._end(error)
                raise

    def exchange(self, payload: bytes, control: OperationControl) -> bytes:
        packet = frame(payload, self._limit)
        with self._held(control):
            if self._state != "running" or self._process is None:
                raise OwnershipConflict("Exchange needs its original running session")
            self._reply.clear()
            try:
                value = exchange(
                    self._process,
                    packet,
                    self._reply,
                    self._stderr,
                    self._limit,
                    self._stderr_limit,
                    control,
                )
                control.checkpoint()
                return value
            except BaseException as error:
                self._end(error)
                raise

    def finish(self, control: OperationControl) -> ProcessTermination:
        """After the protocol's close message, require clean child exit and EOF."""
        with self._held(control):
            if self._state == "finished":
                assert self._termination is not None
                return self._termination
            if self._state != "running" or self._process is None:
                raise OwnershipConflict("Only a running session can finish")
            try:
                wait_exit(self._process, self._stderr, self._stderr_limit, control)
            except BaseException as error:
                self._end(error)
                raise
            return self._end(None, succeeded=True)

    def abort(self, control: OperationControl) -> ProcessTermination:
        """Explicit bounded cleanup; never reconnect/restart a failed original."""
        with self._held(control):
            if (
                self._termination is not None
                and self._termination.state in ("not_started", "reaped")
                and not self._termination.cleanup_errors
            ):
                return self._termination
            return self._end(None)
