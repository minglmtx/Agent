"""Pure parsing of the supported host cgroup-v2 layout, never a cleanup proof."""

from dataclasses import dataclass
import re

_MEMBERSHIP = re.compile(
    r"0::/system\.slice/slurmstepd\.scope/job_([1-9][0-9]{0,19})/"
    r"step_(batch|0|[1-9][0-9]{0,9})/user/task_0\n?"
)


@dataclass(frozen=True)
class CgroupMount:
    mount_id: int
    major: int
    minor: int


def _text(raw: bytes, limit: int) -> str:
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise ValueError("Kernel record must be nonempty bounded bytes")
    return raw.decode("ascii")


def parse_membership(raw: bytes, job_id: str) -> tuple[str, str]:
    match = _MEMBERSHIP.fullmatch(_text(raw, 4096))
    if match is None or match[1] != job_id:
        raise ValueError("Writer is outside the original supported Slurm cgroup")
    return match[2], "/sys/fs/cgroup" + match[0].strip()[3:].removesuffix("/task_0")


def parse_mount(raw: bytes) -> CgroupMount:
    found: list[CgroupMount] = []
    for line in _text(raw, 1024 * 1024).splitlines():
        before, separator, after = line.partition(" - ")
        fields, fs = before.split(), after.split()
        if not separator or len(fields) < 6 or len(fs) < 3:
            raise ValueError("Malformed kernel mount record")
        point = fields[4]
        if point.startswith("/sys/fs/cgroup/"):
            raise ValueError("Nested cgroup mounts are unsupported")
        if fs[0] in ("cgroup", "cgroup2") or point == "/sys/fs/cgroup":
            if (
                fs[0] != "cgroup2"
                or fields[3] != "/"
                or point != "/sys/fs/cgroup"
                or re.fullmatch(r"[1-9][0-9]{0,19}", fields[0]) is None
                or re.fullmatch(r"[0-9]{1,10}:[0-9]{1,10}", fields[2]) is None
            ):
                raise ValueError("Unsupported or aliased cgroup mount")
            major, minor = fields[2].split(":")
            found.append(CgroupMount(int(fields[0]), int(major), int(minor)))
    if len(found) != 1:
        raise ValueError("Exactly one full host cgroup-v2 mount is required")
    return found[0]


def check_host_identity(status: bytes, uid_map: bytes, pid: int, uid: int) -> None:
    """Reject different credentials, PID namespaces and effective capabilities."""
    if type(pid) is not int or pid < 1 or type(uid) is not int or uid <= 0:
        raise ValueError("Expected non-root host credentials")
    fields: dict[str, str] = {}
    for line in _text(status, 65536).splitlines():
        key, separator, value = line.partition(":")
        if not separator or key in fields:
            raise ValueError("Malformed or duplicate process status field")
        fields[key] = value.strip()
    if any(fields.get(key) != str(pid) for key in ("Pid", "Tgid", "NSpid", "NStgid")):
        raise ValueError("Process is not the original host PID/thread group")
    if fields.get("Uid", "").split() != [str(uid)] * 4:
        raise ValueError("Process credentials differ from the original allocation")
    for key in ("CapInh", "CapPrm", "CapEff", "CapAmb"):
        if re.fullmatch(r"0{16}", fields.get(key, "")) is None:
            raise ValueError("Privileged or unknown process capabilities")
    if _text(uid_map, 4096).split() != ["0", "0", "4294967295"]:
        raise ValueError("User namespace is not the host identity mapping")


def check_populated(raw: bytes) -> None:
    _check_population(raw, "1")


def check_quiescent(raw: bytes) -> None:
    _check_population(raw, "0")


def _check_population(raw: bytes, populated: str) -> None:
    fields: dict[str, str] = {}
    for line in _text(raw, 4096).splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] in fields:
            raise ValueError("Malformed or duplicate cgroup event")
        fields[parts[0]] = parts[1]
    if fields != {"populated": populated, "frozen": "0"}:
        raise ValueError(
            "Cgroup subtree population/frozen state differs from required state"
        )


def check_task_processes(raw: bytes, pid: int) -> None:
    values = _text(raw, 65536).splitlines()
    if any(re.fullmatch(r"[1-9][0-9]{0,9}", value) is None for value in values):
        raise ValueError("Malformed cgroup process list")
    if len(values) != len(set(values)) or str(pid) not in values:
        raise ValueError("Original writer is missing from its task cgroup")
