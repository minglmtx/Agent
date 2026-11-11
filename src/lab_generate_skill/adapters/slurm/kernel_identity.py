"""Observe explicitly known local host processes, never discover or signal PIDs.

Kernel I/O remains synchronous and requires external production supervision.
Observation does not establish ownership, descendant containment or authority.
"""

import os
from pathlib import Path
import socket
import sys
from uuid import UUID

from lab_generate_skill.adapters.processes.worker_identity import parse_process_start
from lab_generate_skill.domain.process_identity import ProcessIdentity
from .cgroup_codec import check_host_identity
from .kernel_capture import KernelReadings


def check_observer(readings: KernelReadings, uid: int) -> None:
    if sys.platform != "linux" or type(uid) is not int or uid <= 0:
        raise ValueError("Kernel observation requires non-root Linux host credentials")
    if os.getresuid() != (uid,) * 3:
        raise ValueError("Writer OS credentials differ from the non-root allocation")
    check_process_credentials(readings, os.getpid(), uid)


def check_process_credentials(readings: KernelReadings, pid: int, uid: int) -> None:
    if type(pid) is not int or pid <= 0:
        raise ValueError("Expected a known positive host process ID")
    proc = Path("/proc") / str(pid)
    check_host_identity(
        readings.read(proc / "status", 65536),
        readings.read(proc / "uid_map", 4096),
        pid,
        uid,
    )


def read_process_identity(
    readings: KernelReadings, pid: int, uid: int
) -> ProcessIdentity:
    """Read credentials and incarnation for a known PID; caller rechecks stability."""
    if sys.platform != "linux" or os.getresuid() != (uid,) * 3 or uid == 0:
        raise ValueError("Writer OS credentials differ from the non-root allocation")
    check_process_credentials(readings, pid, uid)
    return ProcessIdentity(
        node_id=socket.gethostname(),
        boot_id=str(
            UUID(
                readings.read(Path("/proc/sys/kernel/random/boot_id"), 128)
                .decode("ascii")
                .strip()
            )
        ),
        process_id=pid,
        start_ticks=parse_process_start(
            readings.read(Path("/proc") / str(pid) / "stat", 16384), pid
        ),
    )
