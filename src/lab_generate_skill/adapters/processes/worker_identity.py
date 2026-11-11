"""Observe this Linux evidence worker incarnation inside the supervised child.

PID alone is insufficient: retain hostname, boot UUID and /proc start ticks.
This is local identity observation, not a writer-tree termination or permission
proof. No caller-selected proc root and no fallback identity on read failure.
"""

import os
import socket
import sys
from pathlib import Path
from uuid import UUID
from lab_generate_skill.domain.evidence_sessions import EvidenceWorkerInstance
from lab_generate_skill.domain.process_identity import ProcessIdentity


def parse_process_start(raw: bytes, process_id: int) -> int:
    """Parse field22 after the final ')' of comm; comm may contain spaces/')."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 16384:
        raise ValueError("Process stat must be bounded bytes")
    if type(process_id) is not int or process_id <= 0:
        raise ValueError("Process identity must be a positive integer")
    prefix, separator, rest = raw.partition(b" (")
    if not separator or prefix != str(process_id).encode():
        raise ValueError("Process stat belongs to another PID")
    _, closing, tail = rest.rpartition(b") ")
    fields = tail.split()
    if not closing or len(fields) < 20 or len(fields[0]) != 1:
        raise ValueError("Process stat is truncated")
    if not fields[19].isdigit():
        raise ValueError("Process start ticks must be positive decimal")
    start = int(fields[19])
    if start <= 0:
        raise ValueError("Process start ticks must be positive")
    return start


def _bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError("Local process identity outside bounds")
    return raw


def current_process_identity() -> ProcessIdentity:
    if sys.platform != "linux":
        raise RuntimeError("Evidence worker identity requires Linux procfs")
    pid = os.getpid()
    start = parse_process_start(_bounded(Path("/proc/self/stat"), 16384), pid)
    boot = str(
        UUID(
            _bounded(Path("/proc/sys/kernel/random/boot_id"), 128)
            .decode("ascii")
            .strip()
        )
    )
    return ProcessIdentity(
        node_id=socket.gethostname(),
        boot_id=boot,
        process_id=pid,
        start_ticks=start,
    )


def current_evidence_worker() -> EvidenceWorkerInstance:
    """Keep the original evidence wire schema; share the same /proc observer."""
    return EvidenceWorkerInstance.model_validate(
        current_process_identity().model_dump(exclude={"schema_version"})
    )
