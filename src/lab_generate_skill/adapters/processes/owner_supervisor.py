"""Single-threaded Linux parent monitor for one fixed model child.

No threads, arbitrary exec, restart, storage or descendant-clean claim. Model
work runs only after the child arms kernel parent-death protection. Parent polls
pidfds independently of child Python/GIL/native I/O; after failure only the exact
owned direct child is killed, with bounded reap. Slurm retains tree containment.
"""

import ctypes
import os
import select
import signal
import threading
import time
from collections.abc import Callable
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .worker_identity import current_process_identity
from .linux_pidfd import open_pidfd, kill_pidfd
from .remote_errors import describe_error
from .owner_pidfd import pinned_owner, ended, close_owned

_SET_PDEATHSIG = 1
_GET_PDEATHSIG = 2


def _prctl(option: int, value: object) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(option, value, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, "Parent-death protection failed")


def arm_parent_death(parent_pid: int) -> None:
    if type(parent_pid) is not int or parent_pid <= 0 or parent_pid == os.getpid():
        raise ValueError("Expected a distinct original parent")
    _prctl(_SET_PDEATHSIG, signal.SIGKILL)
    if os.getppid() != parent_pid:
        raise OwnershipConflict("Supervisor died before child guard was armed")


def observed_guard(
    controller: ProcessIdentity,
    supervisor: ProcessIdentity,
    owner_fd: int,
    control: OperationControl,
) -> ProcessOwnerGuard:
    control.checkpoint()
    actual_signal = ctypes.c_int()
    _prctl(_GET_PDEATHSIG, ctypes.byref(actual_signal))
    if (
        actual_signal.value != signal.SIGKILL
        or os.getppid() != supervisor.process_id
        or ended(owner_fd)
    ):
        raise OwnershipConflict("Original controller/supervisor guard is not live")
    result = ProcessOwnerGuard(
        controller=controller, supervisor=supervisor, worker=current_process_identity()
    )
    control.checkpoint()
    return result


def _kill_and_reap(pid: int, fd: int) -> None:
    try:
        kill_pidfd(fd)
    except ProcessLookupError:
        pass
    until = time.monotonic() + 2
    while time.monotonic() < until:
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return
        time.sleep(0.01)
    raise TimeoutError("Original guarded child termination remains unconfirmed")


def supervise_owner(
    controller: ProcessIdentity,
    control: OperationControl,
    run_child: Callable[[ProcessIdentity, int], int],
) -> int:
    """Only trusted fixed bootstrap supplies run_child, never wire inputs."""
    controller = ProcessIdentity.model_validate(controller)
    if not callable(run_child):
        raise ValueError("A fixed child function is required")
    if threading.active_count() != 1:
        raise RuntimeError("Fork guard must start before model/native threads")
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise RuntimeError("Supervisor requires sole ownership of child reaping")
    with pinned_owner(controller, control) as owner_fd:
        supervisor = current_process_identity()
        pid = os.fork()
        if pid == 0:
            code = 125
            try:
                arm_parent_death(supervisor.process_id)
                if ended(owner_fd):
                    raise OwnershipConflict("Controller ended before model child start")
                code = run_child(supervisor, owner_fd)
                if type(code) is not int or not 0 <= code <= 255:
                    raise ValueError("Guarded child returned an invalid exit code")
            except BaseException as error:
                code = 125
                # Do not serialize credentials, model inputs or foreign traceback.
                os.write(
                    2,
                    b"GENERATOR_GUARDED_CHILD_FAILED "
                    + describe_error(error).model_dump_json().encode()
                    + b"\n",
                )
            finally:
                os._exit(code)
        fds: list[int] = []
        primary: BaseException | None = None
        reaped = False
        child_fd: int | None = None
        try:
            # The unreaped direct child cannot have its PID reused here.
            child_fd = open_pidfd(pid)
            fds.append(child_fd)
            poll = select.poll()
            poll.register(owner_fd, select.POLLIN)
            poll.register(child_fd, select.POLLIN)
            while True:
                ready = poll.poll(100)
                if any(
                    flags & (select.POLLNVAL | select.POLLERR) for _, flags in ready
                ):
                    raise OSError("Original supervision descriptor failed")
                if any(fd == owner_fd for fd, _ in ready):
                    raise OwnershipConflict("Original controller ended")
                if any(fd == child_fd for fd, _ in ready):
                    actual, status = os.waitpid(pid, os.WNOHANG)
                    if actual == pid:
                        reaped = True
                        code = os.waitstatus_to_exitcode(status)
                        return code if code >= 0 else 128 - code
        except BaseException as error:
            primary = error
            raise
        finally:
            errors: list[BaseException] = []
            if not reaped:
                try:
                    if child_fd is None:
                        # Opening pidfd failed before a handle existed. Owned child
                        # is still unreaped: its original numeric PID cannot reuse.
                        os.kill(pid, signal.SIGKILL)
                        until = time.monotonic() + 2
                        while os.waitpid(pid, os.WNOHANG)[0] == 0:
                            if time.monotonic() >= until:
                                raise TimeoutError("Guard startup child not reaped")
                            time.sleep(0.01)
                    else:
                        _kill_and_reap(pid, child_fd)
                except BaseException as cleanup:
                    errors.append(cleanup)
            try:
                close_owned(fds)
            except BaseException as cleanup:
                errors.append(cleanup)
            if errors:
                raise BaseExceptionGroup(
                    "Owner supervisor and cleanup failed",
                    ([primary] if primary is not None else []) + errors,
                ) from None
