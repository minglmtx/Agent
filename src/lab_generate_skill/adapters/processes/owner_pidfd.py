"""Pin a supplied live local incarnation; never discover owners or signal a PID.

Linux proc reads and pidfd_open are synchronous. This is not an outer hard-I/O
supervisor. Caller owns returned descriptor; all close errors preserve primary.
"""

import os
import select
from contextlib import contextmanager
from collections.abc import Iterator
from .linux_pidfd import open_pidfd
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings


def ended(fd: int) -> bool:
    poll = select.poll()
    poll.register(fd, select.POLLIN)
    result = poll.poll(0)
    if any(flags & select.POLLNVAL for _, flags in result):
        raise OSError("Invalid original pidfd")
    return bool(result)


def close_owned(fds: list[int], primary: BaseException | None = None) -> None:
    errors: list[BaseException] = []
    while fds:
        fd = fds.pop()
        try:
            os.close(fd)
        except BaseException as error:
            errors.append(error)
    if errors:
        raise BaseExceptionGroup(
            "Owner guard and descriptor cleanup failed",
            ([primary] if primary is not None else []) + errors,
        ) from None


@contextmanager
def pinned_owner(expected: ProcessIdentity, control: OperationControl) -> Iterator[int]:
    expected = ProcessIdentity.model_validate(expected)
    if expected.process_id == os.getpid():
        raise OwnershipConflict("Owner supervisor cannot monitor itself")
    readings = KernelReadings(control)
    fds: list[int] = []
    primary: BaseException | None = None
    try:
        before = read_process_identity(readings, expected.process_id, os.getuid())
        if before != expected:
            raise OwnershipConflict("Controller differs from original incarnation")
        fd = open_pidfd(expected.process_id)
        fds.append(fd)
        if (
            ended(fd)
            or read_process_identity(readings, expected.process_id, os.getuid())
            != expected
        ):
            raise OwnershipConflict("Controller changed or ended while pinning")
        control.checkpoint()
        yield fd
    except BaseException as error:
        primary = error
        setattr(error, "slurm_kernel_capture", readings.capture())
        raise
    finally:
        close_owned(fds, primary)
