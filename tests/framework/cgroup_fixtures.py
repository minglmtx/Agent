"""Explicit synthetic kernel records; actual Linux observation is tested separately."""

from lab_generate_skill.domain.process_identity import ProcessIdentity

PID = 123
UID = 1000
BOOT = "4b4dd338-23e5-465e-95d6-f21a9d346b94"
USER = "/sys/fs/cgroup/system.slice/slurmstepd.scope/job_123/step_batch/user"
CGROUP = b"0::/system.slice/slurmstepd.scope/job_123/step_batch/user/task_0\n"
MOUNT = b"138 85 0:26 / /sys/fs/cgroup rw,nosuid,nodev,noexec - cgroup2 cgroup2 rw\n"
UID_MAP = b"0 0 4294967295\n"
STATUS = b"Pid:\t123\nTgid:\t123\nNSpid:\t123\nNStgid:\t123\nUid:\t1000 1000 1000 1000\nCapInh:\t0000000000000000\nCapPrm:\t0000000000000000\nCapEff:\t0000000000000000\nCapAmb:\t0000000000000000\n"
STAT = ("123 (worker) S " + " ".join(["0"] * 18 + ["42"] + ["0"] * 10) + "\n").encode()


def writer() -> ProcessIdentity:
    return ProcessIdentity(node_id="node", boot_id=BOOT, process_id=PID, start_ticks=42)


class Control:
    def checkpoint(self) -> float:
        return 100.0

    def wait(self, seconds: float) -> None:
        raise AssertionError("No waiting in a kernel observation")
