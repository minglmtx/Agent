"""Combined kernel observation under injected faults and an actual Slurm job."""

from dataclasses import replace
import base64
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
from typing import Any

import pytest

from lab_generate_skill.adapters.slurm import linux_cgroups as module
from lab_generate_skill.adapters.slurm import kernel_capture as captures
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.adapters.slurm.kernel_files import KernelControl, KernelRead
from lab_generate_skill.adapters.slurm.accounting import (
    ACCOUNTING_FORMAT,
    parse_accounting,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from cgroup_fixtures import (
    BOOT,
    CGROUP,
    MOUNT,
    PID,
    STAT,
    STATUS,
    UID,
    UID_MAP,
    USER,
    Control,
    writer,
)
from test_slurm_probe import execution


@pytest.fixture
def kernel(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    values = {
        f"/proc/{PID}/status": STATUS,
        f"/proc/{PID}/uid_map": UID_MAP,
        "/proc/sys/kernel/random/boot_id": (BOOT + "\n").encode(),
        f"/proc/{PID}/stat": STAT,
        f"/proc/{PID}/cgroup": CGROUP,
        f"/proc/{PID}/mountinfo": MOUNT,
        USER + "/cgroup.type": b"domain\n",
        USER + "/cgroup.events": b"populated 1\nfrozen 0\n",
        USER + "/task_0/cgroup.type": b"domain\n",
        USER + "/task_0/cgroup.events": b"populated 1\nfrozen 0\n",
        USER + "/task_0/cgroup.procs": b"123\n",
    }
    monkeypatch.setattr(os, "getpid", lambda: PID)
    monkeypatch.setattr(os, "getresuid", lambda: (UID, UID, UID))
    monkeypatch.setattr(socket, "gethostname", lambda: "node")

    def read(path: Path, limit: int, control: Any) -> KernelRead:
        control.checkpoint()
        raw = values[str(path)]
        assert len(raw) <= limit
        return KernelRead(str(path), raw, True)

    inodes: dict[str, int] = {}

    def inspect(path: Path, control: Any, *, directory: bool) -> KernelControl:
        control.checkpoint()
        inode = inodes.setdefault(str(path), len(inodes) + 100)
        return KernelControl(
            str(path),
            os.makedev(0, 26),
            inode,
            0,
            0,
            (stat.S_IFDIR | 0o755) if directory else (stat.S_IFREG | 0o644),
            False,
        )

    monkeypatch.setattr(captures, "read_kernel_file", read)
    monkeypatch.setattr(captures, "inspect_control", inspect)
    return values


def test_observation_and_repeated_read(kernel: dict[str, bytes]) -> None:
    first = module.observe_current_cgroup(execution(), writer(), Control())
    again = module.observe_current_cgroup(execution(), writer(), Control())
    assert first == again
    assert first.membership.writer == writer()
    assert first.membership.user_path == USER
    assert first.membership.step_id == "batch"
    assert first.membership.user_inode != first.membership.task_inode
    paths = [x.path for x in first.capture.controls]
    for suffix in ("", "/cgroup.procs", "/cgroup.threads"):
        assert paths.count("/sys/fs/cgroup" + suffix) == 2
    assert paths.count("/") == 2
    assert len(first.capture.reads) == 17


@pytest.mark.parametrize(
    "field,value",
    [
        ("start_ticks", 43),
        ("node_id", "other"),
        ("process_id", 124),
        ("boot_id", "00000000-0000-0000-0000-000000000000"),
    ],
)
def test_original_writer_mismatch(
    kernel: dict[str, bytes], field: str, value: object
) -> None:
    changed = writer().model_copy(update={field: value})
    with pytest.raises(ValueError) as caught:
        module.observe_current_cgroup(execution(), changed, Control())
    assert isinstance(getattr(caught.value, "slurm_kernel_capture"), KernelCapture)


@pytest.mark.parametrize(
    "path,value",
    [
        (
            f"/proc/{PID}/status",
            STATUS.replace(b"1000 1000 1000 1000", b"1000 0 1000 1000"),
        ),
        (f"/proc/{PID}/cgroup", CGROUP.replace(b"job_123", b"job_124")),
        (f"/proc/{PID}/mountinfo", MOUNT.replace(b"0:26", b"0:27")),
        (USER + "/cgroup.type", b"domain threaded\n"),
        (USER + "/cgroup.events", b"populated 0\nfrozen 0\n"),
        (USER + "/task_0/cgroup.procs", b"456\n"),
    ],
)
def test_wrong_kernel_facts(kernel: dict[str, bytes], path: str, value: bytes) -> None:
    kernel[path] = value
    with pytest.raises(ValueError) as caught:
        module.observe_current_cgroup(execution(), writer(), Control())
    capture = getattr(caught.value, "slurm_kernel_capture")
    assert any(r.path == path and r.content == value for r in capture.reads)


def test_changed_cgroup_between_snapshots(
    kernel: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = getattr(captures, "read_kernel_file")
    calls = 0

    def read(path: Path, limit: int, control: Any) -> KernelRead:
        nonlocal calls
        if str(path) == f"/proc/{PID}/cgroup":
            calls += 1
            if calls == 2:
                kernel[str(path)] = CGROUP.replace(b"step_batch", b"step_0")
        result: KernelRead = original(path, limit, control)
        return result

    monkeypatch.setattr(captures, "read_kernel_file", read)
    with pytest.raises(ValueError, match="changed during"):
        module.observe_current_cgroup(execution(), writer(), Control())


@pytest.mark.parametrize(
    "target", [USER, USER + "/cgroup.procs", "/sys/fs/cgroup/cgroup.threads"]
)
def test_controls_rechecked_after_reads(
    kernel: dict[str, bytes], monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    original = getattr(captures, "inspect_control")
    calls = 0

    def inspect(path: Path, control: Any, *, directory: bool) -> KernelControl:
        nonlocal calls
        record: KernelControl = original(path, control, directory=directory)
        if str(path) == target:
            calls += 1
            if calls == 2:
                return replace(record, inode=record.inode + 10000)
        return record

    monkeypatch.setattr(captures, "inspect_control", inspect)
    with pytest.raises(ValueError, match="path identity changed"):
        module.observe_current_cgroup(execution(), writer(), Control())


def test_partial_read_failure_retained(
    kernel: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = getattr(captures, "read_kernel_file")
    failure = OSError("partial kernel read")
    setattr(
        failure,
        "kernel_read_capture",
        KernelRead(USER + "/cgroup.events", b"pop", False),
    )

    def read(path: Path, limit: int, control: Any) -> KernelRead:
        if str(path) == USER + "/cgroup.events":
            raise failure
        result: KernelRead = original(path, limit, control)
        return result

    monkeypatch.setattr(captures, "read_kernel_file", read)
    with pytest.raises(OSError) as caught:
        module.observe_current_cgroup(execution(), writer(), Control())
    assert caught.value is failure
    capture = getattr(failure, "slurm_kernel_capture")
    assert capture.reads[-1].content == b"pop" and not capture.reads[-1].complete


def test_os_credential_rejection_before_reads(
    kernel: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "getresuid", lambda: (UID, 0, UID))
    with pytest.raises(ValueError) as caught:
        module.observe_current_cgroup(execution(), writer(), Control())
    assert getattr(caught.value, "slurm_kernel_capture").reads == ()


def test_missing_control_path_is_not_an_empty_tree(
    kernel: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = getattr(captures, "inspect_control")
    target = USER + "/cgroup.procs"

    def inspect(path: Path, control: Any, *, directory: bool) -> KernelControl:
        if str(path) == target:
            raise FileNotFoundError("original control missing")
        record: KernelControl = original(path, control, directory=directory)
        return record

    monkeypatch.setattr(captures, "inspect_control", inspect)
    with pytest.raises(FileNotFoundError) as caught:
        module.observe_current_cgroup(execution(), writer(), Control())
    assert getattr(caught.value, "slurm_kernel_capture").failed_control_path == target


def actual_slurm_execution() -> tuple[SlurmExecutionIdentity, bytes]:
    job, cluster = os.environ.get("SLURM_JOB_ID"), os.environ.get("SLURM_CLUSTER_NAME")
    if job is None or cluster is None:
        pytest.skip("actual kernel observation requires a Slurm compute allocation")
    assert re.fullmatch(r"[1-9][0-9]{0,19}", job)
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", cluster)
    result = subprocess.run(
        [
            "/usr/bin/sacct",
            "--clusters=" + cluster,
            "-X",
            "-D",
            "-n",
            "-P",
            "--jobs=" + job,
            "--format=" + ACCOUNTING_FORMAT,
        ],
        env={
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
            "SLURM_TIME_FORMAT": "%s",
        },
        capture_output=True,
        timeout=20,
        check=True,
    )
    lines = result.stdout.decode().strip().splitlines()
    assert len(lines) == 1
    fields = lines[0].split("|")
    assert len(fields) == 11
    identity = SlurmExecutionIdentity(
        cluster=fields[0],
        job_id=fields[1],
        raw_job_id=fields[2],
        database_index=fields[3],
        uid=int(fields[4]),
        submitted_at_epoch=int(fields[5]),
        started_at_epoch=int(fields[6]),
        restart_count=int(fields[8]),
    )
    assert (
        identity.job_id == job
        and identity.cluster == cluster
        and identity.uid == os.getuid()
    )
    assert parse_accounting(result.stdout, identity).state == "RUNNING"
    return identity, result.stdout


def test_actual_slurm_current_writer() -> None:
    identity, accounting_raw = actual_slurm_execution()
    actual_writer = current_process_identity()
    observed = module.observe_current_cgroup(identity, actual_writer, Control())
    again = module.observe_current_cgroup(identity, actual_writer, Control())
    assert observed.membership == again.membership
    assert observed.membership.writer.process_id == os.getpid()
    assert observed.membership.job_id == identity.job_id
    assert observed.membership.step_id == "batch"
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "kernel-observation.json"
    payload = {
        "schema": "actual-cgroup-observation-check/1",
        "execution": identity.model_dump(mode="json"),
        "membership": observed.membership.model_dump(mode="json"),
        "raw_accounting_base64": base64.b64encode(accounting_raw).decode(),
        "raw_reads": [
            {
                "path": r.path,
                "complete": r.complete,
                "content_base64": base64.b64encode(r.content).decode(),
            }
            for r in observed.capture.reads
        ],
        "controls": [vars(c) for c in observed.capture.controls],
        "repeat_membership_matches": True,
        "production_authority": False,
    }
    with output.open("x") as stream:
        os.chmod(output, 0o600)
        json.dump(payload, stream, indent=2)
