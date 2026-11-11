"""Bounded POSIX transport for trusted commands with optional memory-only stdin.

No shell, inherited credentials, implicit retry or unbounded pipe buffering.
On failure kill the command process group and bound direct-child reaping with an
independent cleanup timeout. This is NOT containment/termination proof for task
writers; escaped sessions and uninterruptible process creation need supervision.
"""

import math
import os
import selectors
import subprocess
from dataclasses import replace

from lab_generate_skill.ports.lifecycle import OperationControl


from .capture import (
    CommandCapture as CommandCapture,
    CommandFailure as CommandFailure,
    ProcessTermination,
)
from .cleanup import finish_process


class ProcessRunner:
    def __init__(
        self, *, max_output_bytes: int = 1024 * 1024, reap_timeout: float = 2.0
    ) -> None:
        if (
            type(max_output_bytes) is not int
            or not 1 <= max_output_bytes <= 128 * 1024 * 1024
        ):
            raise ValueError("Output bound must be an integer between 1 and 128 MiB")
        if (
            isinstance(reap_timeout, bool)
            or not isinstance(reap_timeout, (float, int))
            or not 0 < reap_timeout <= 10
            or not math.isfinite(reap_timeout)
        ):
            raise ValueError("Reap timeout must be finite and in (0, 10]")
        self._limit, self._reap_timeout = max_output_bytes, reap_timeout

    def run(
        self,
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        if (
            type(argv) is not tuple
            or not argv
            or any(type(arg) is not str or not arg or "\0" in arg for arg in argv)
            or not os.path.isabs(argv[0])
        ):
            raise ValueError("Command requires an absolute binary and exact argv tuple")
        if stdin_bytes is not None and (
            type(stdin_bytes) is not bytes or len(stdin_bytes) > 256 * 1024 * 1024
        ):
            raise ValueError("Stdin must be bytes bounded to 256 MiB")
        control.checkpoint()
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL if stdin_bytes is None else subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                close_fds=True,
                env={
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "TZ": "UTC",
                    "SLURM_TIME_FORMAT": "%s",
                },
            )
        except OSError as error:
            raise CommandFailure(
                "START_FAILED",
                CommandCapture(
                    argv,
                    None,
                    b"",
                    b"",
                    False,
                    ProcessTermination(None, "not_started", None, False),
                ),
            ) from error
        assert process.stdout is not None and process.stderr is not None
        output = [bytearray(), bytearray()]
        primary: BaseException | None = None
        success = False
        sent = 0
        try:
            with selectors.DefaultSelector() as selector:
                for index, stream in enumerate((process.stdout, process.stderr)):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, index)
                if process.stdin is not None:
                    os.set_blocking(process.stdin.fileno(), False)
                    selector.register(process.stdin, selectors.EVENT_WRITE, 2)
                while selector.get_map() or process.poll() is None:
                    remaining = control.checkpoint()
                    for key, _ in selector.select(min(remaining, 0.05)):
                        if key.data == 2:
                            assert stdin_bytes is not None and process.stdin is not None
                            if sent < len(stdin_bytes):
                                sent += os.write(
                                    key.fd, stdin_bytes[sent : sent + 65536]
                                )
                            if sent == len(stdin_bytes):
                                selector.unregister(process.stdin)
                                process.stdin.close()
                            continue
                        available = self._limit - sum(map(len, output))
                        chunk = os.read(key.fd, min(65536, available + 1))
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        output[key.data].extend(chunk[:available])
                        if len(chunk) > available:
                            raise CommandFailure(
                                "OUTPUT_LIMIT",
                                CommandCapture(
                                    argv,
                                    process.returncode,
                                    bytes(output[0]),
                                    bytes(output[1]),
                                    False,
                                ),
                            )
                control.checkpoint()
            success = True
        except BaseException as error:
            # Keep the original leader unreaped until group cleanup. poll() here
            # would release its PID before signalling remaining pipe holders;
            # a numeric PGID cannot safely be signalled after that point.
            if isinstance(error, CommandFailure):
                primary = error
            elif isinstance(error, Exception):
                primary = CommandFailure(
                    getattr(error, "reason_code", "TRANSPORT_FAILED"),
                    CommandCapture(
                        argv,
                        process.returncode,
                        bytes(output[0]),
                        bytes(output[1]),
                        False,
                    ),
                )
            else:
                primary = error
            if primary is error:
                raise
            raise primary from error
        finally:
            termination, cleanup = finish_process(
                process, succeeded=success, reap_timeout=self._reap_timeout
            )
            capture = CommandCapture(
                argv,
                process.returncode,
                bytes(output[0]),
                bytes(output[1]),
                success,
                termination,
            )
            if isinstance(primary, CommandFailure):
                # Keep the original output/returncode observation, adding final
                # cleanup facts without replacing the original cause.
                primary.capture = replace(primary.capture, termination=termination)
            elif isinstance(primary, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                # Preserve stop-exception identity; no conversion into a routine
                # Exception that callers might ignore and continue processing.
                setattr(primary, "command_capture", capture)
            if success and termination.state != "reaped":
                cleanup.insert(0, RuntimeError("Command exit was not confirmed"))
            if cleanup:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Command and cleanup failed", [primary, *cleanup]
                    ) from None
                raise BaseExceptionGroup(
                    "Command cleanup failed",
                    [CommandFailure("CLEANUP_FAILED", capture), *cleanup],
                )
        return capture
