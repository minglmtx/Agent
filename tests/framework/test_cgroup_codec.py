"""Host layout, credential and live population facts; pure input boundaries."""

import pytest

from lab_generate_skill.adapters.slurm.cgroup_codec import (
    check_host_identity,
    check_populated,
    check_task_processes,
    parse_membership,
    parse_mount,
)
from cgroup_fixtures import CGROUP, MOUNT, PID, STATUS, UID, UID_MAP, USER


def test_supported_host_layout() -> None:
    assert parse_membership(CGROUP, "123") == ("batch", USER)
    assert parse_membership(CGROUP.replace(b"step_batch", b"step_0"), "123") == (
        "0",
        USER.replace("step_batch", "step_0"),
    )
    assert (
        parse_membership(CGROUP.replace(b"step_batch", b"step_999"), "123")[0] == "999"
    )
    assert parse_mount(MOUNT).mount_id == 138
    assert (parse_mount(MOUNT).major, parse_mount(MOUNT).minor) == (0, 26)
    check_host_identity(STATUS, UID_MAP, PID, UID)
    check_populated(b"frozen 0\npopulated 1\n")
    check_task_processes(b"456\n123\n", PID)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        CGROUP * 2,
        CGROUP.replace(b"job_123", b"job_124"),
        CGROUP.replace(b"step_batch", b"step_extern"),
        CGROUP.replace(b"step_batch", b"step_00"),
        CGROUP.replace(b"task_0", b"task_1"),
        CGROUP.replace(b"0::", b"1:cpu:"),
        CGROUP.replace(b"user/task_0", b"user/../task_0"),
        CGROUP + b"\x00",
        b"\xff",
        b" " * 4097,
    ],
)
def test_membership_rejects_other_or_ambiguous_roots(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_membership(raw, "123")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        MOUNT * 2,
        MOUNT.replace(b"cgroup2", b"cgroup"),
        MOUNT.replace(b" / /sys", b" /delegated /sys"),
        MOUNT.replace(b"/sys/fs/cgroup", b"/alternate"),
        MOUNT + b"139 138 0:26 /job /sys/fs/cgroup/job rw - cgroup2 cgroup2 rw\n",
        MOUNT.replace(b"138", b"0", 1),
        MOUNT.replace(b"0:26", b"unknown"),
        MOUNT.replace(b" - ", b" "),
        MOUNT.replace(b"cgroup2 cgroup2", b"tmpfs tmpfs"),
        b"\xff",
        b" " * (1024 * 1024 + 1),
    ],
)
def test_mount_requires_one_host_mount(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_mount(raw)


@pytest.mark.parametrize(
    "old,new",
    [
        (b"Pid:\t123", b"Pid:\t124"),
        (b"Tgid:\t123", b"Tgid:\t124"),
        (b"NSpid:\t123", b"NSpid:\t123 1"),
        (b"NStgid:\t123", b"NStgid:\t1"),
        (b"1000 1000 1000 1000", b"1000 0 1000 1000"),
        (b"CapEff:\t0000000000000000", b"CapEff:\t0000000000200000"),
        (b"CapAmb:\t0000000000000000", b""),
        (b"CapInh:\t0000000000000000", b"CapInh:\t0"),
        (b"CapPrm:\t0000000000000000", b"CapPrm:\t0000000000000001"),
    ],
)
def test_status_rejects_changed_credentials(old: bytes, new: bytes) -> None:
    with pytest.raises(ValueError):
        check_host_identity(STATUS.replace(old, new), UID_MAP, PID, UID)


@pytest.mark.parametrize(
    "status,uid_map",
    [
        (STATUS + b"Pid: 123\n", UID_MAP),
        (b"malformed", UID_MAP),
        (STATUS, b"0 1000 1\n"),
        (STATUS, UID_MAP * 2),
        (STATUS, b""),
    ],
)
def test_status_and_uid_mapping_ambiguity(status: bytes, uid_map: bytes) -> None:
    with pytest.raises(ValueError):
        check_host_identity(status, uid_map, PID, UID)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"populated 0\nfrozen 0\n",
        b"populated 1\nfrozen 1\n",
        b"populated 1\n",
        b"populated 1\nfrozen 0\npopulated 1\n",
        b"populated true\nfrozen false\n",
        b"populated 1 0\n",
        b"\xff",
    ],
)
def test_empty_frozen_or_unknown_subtree_rejected(raw: bytes) -> None:
    with pytest.raises(ValueError):
        check_populated(raw)


@pytest.mark.parametrize(
    "raw", [b"", b"456\n", b"123\n123\n", b"0123\n", b"-1\n", b"123\n0\n"]
)
def test_missing_or_ambiguous_process_list(raw: bytes) -> None:
    with pytest.raises(ValueError):
        check_task_processes(raw, PID)
