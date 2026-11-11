"""Independent bounded child reaping; primary failures stay owned by the caller.

Return observed termination and every original cleanup exception. Sending
SIGKILL is not evidence of exit. Once this Popen has reaped the child, never
signal its reusable PID/PGID again; only close owned stream objects. This does
not establish that descendants ended. No task/provider resources are closed.
"""

import os
import signal
import subprocess
from .capture import ProcessTermination


def finish_process(
    process: subprocess.Popen[bytes], *, succeeded: bool, reap_timeout: float
) -> tuple[ProcessTermination, list[BaseException]]:
    errors: list[BaseException] = []
    kill_requested = not succeeded and process.returncode is None
    if kill_requested:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except BaseException as error:
            errors.append(error)
        try:
            process.wait(timeout=reap_timeout)
        except BaseException as error:
            errors.append(error)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is None or stream.closed:
            continue
        try:
            stream.close()
        except BaseException as error:
            errors.append(error)
    return (
        ProcessTermination(
            process_id=process.pid,
            state="reaped" if process.returncode is not None else "unconfirmed",
            returncode=process.returncode,
            kill_requested=kill_requested,
            cleanup_errors=tuple(type(error).__name__ for error in errors),
        ),
        errors,
    )
