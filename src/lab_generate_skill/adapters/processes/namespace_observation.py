"""Read only direct children of an original Apptainer launcher, never global PIDs.

The fixed containall deployment has one direct child namespace init. Unsupported
layouts, transient reads, ambiguous candidates and changed identities fail closed.
"""

from pathlib import Path
from dataclasses import dataclass
import os
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings
from .worker_identity import parse_process_start


@dataclass(frozen=True)
class NamespaceChild:
    identity: ProcessIdentity
    parent_pid: int
    namespace_pids: tuple[int, ...]


def parse_child(
    status: bytes, stat: bytes, pid: int, uid: int, launcher: ProcessIdentity
) -> NamespaceChild:
    if type(pid) is not int or pid <= 0 or type(uid) is not int or uid <= 0:
        raise ValueError("Expected positive child PID and non-root owner")
    if type(status) is not bytes or not 0 < len(status) <= 65536:
        raise ValueError("Bounded child status required")
    fields: dict[str, str] = {}
    for line in status.decode("ascii").splitlines():
        key, separator, value = line.partition(":")
        if not separator or key in fields:
            raise ValueError("Malformed child status")
        fields[key] = value.strip()
    if (
        fields.get("Pid") != str(pid)
        or fields.get("Tgid") != str(pid)
        or fields.get("Uid", "").split() != [str(uid)] * 4
    ):
        raise ValueError("Child credentials/PID changed")
    values = fields.get("NSpid", "").split()
    if (
        not values
        or len(values) > 2
        or any(not x.isdecimal() or int(x) <= 0 for x in values)
    ):
        raise ValueError("Unsupported child namespace depth or IDs")
    nspid = tuple(int(x) for x in values)
    if nspid[0] != pid or fields.get("NStgid", "").split() != values:
        raise ValueError("Child namespace identity differs")
    start = parse_process_start(stat, pid)
    parent = fields.get("PPid", "")
    if not parent.isdecimal() or int(parent) != launcher.process_id:
        raise ValueError("Namespace child left original launcher")
    return NamespaceChild(
        ProcessIdentity(
            node_id=launcher.node_id,
            boot_id=launcher.boot_id,
            process_id=pid,
            start_ticks=start,
        ),
        int(parent),
        nspid,
    )


def child(
    readings: KernelReadings, pid: int, launcher: ProcessIdentity
) -> NamespaceChild:
    root = Path("/proc") / str(pid)
    return parse_child(
        readings.read(root / "status", 65536),
        readings.read(root / "stat", 16384),
        pid,
        os.getuid(),
        launcher,
    )


def direct_children(readings: KernelReadings, pid: int) -> tuple[int, ...]:
    root = Path("/proc") / str(pid) / "task"
    readings.control.checkpoint()
    tids = tuple(root.iterdir())
    if not 0 < len(tids) <= 128:
        raise ValueError("Launcher thread inventory outside bounds")
    found: set[int] = set()
    for tid in tids:
        if not tid.name.isdecimal():
            raise ValueError("Unexpected launcher task entry")
        values = readings.read(tid / "children", 4096).decode("ascii").split()
        if any(not x.isdecimal() or int(x) <= 0 for x in values):
            raise ValueError("Invalid launcher child IDs")
        found.update(int(x) for x in values)
        if len(found) > 128:
            raise ValueError("Launcher children outside bound")
    return tuple(sorted(found))


def parse_launcher(
    status: bytes,
    stat: bytes,
    uid_map: bytes,
    gid_map: bytes,
    pid: int,
    uid: int,
    gid: int,
    observer: ProcessIdentity,
) -> ProcessIdentity:
    """Accept host launcher or exact one-UID/GID Apptainer user namespace.

    Namespace-local capabilities are not host privileges. No root/multiple/range
    mapping is accepted through this branch; original host checks stay strict.
    """
    from lab_generate_skill.adapters.slurm.cgroup_codec import check_host_identity

    observed = parse_child(status, stat, pid, uid, observer)
    if observed.namespace_pids != (pid,):
        raise ValueError("Launcher must remain visible in original host PID namespace")
    if uid_map.split() == [b"0", b"0", b"4294967295"]:
        check_host_identity(status, uid_map, pid, uid)
    elif uid_map.split() != [str(uid).encode()] * 2 + [b"1"] or gid_map.split() != [
        str(gid).encode()
    ] * 2 + [b"1"]:
        raise ValueError("Launcher user namespace must map only the original owner")
    return observed.identity


def launcher(
    readings: KernelReadings, pid: int, observer: ProcessIdentity
) -> ProcessIdentity:
    root = Path("/proc") / str(pid)
    return parse_launcher(
        readings.read(root / "status", 65536),
        readings.read(root / "stat", 16384),
        readings.read(root / "uid_map", 4096),
        readings.read(root / "gid_map", 4096),
        pid,
        os.getuid(),
        os.getgid(),
        observer,
    )
