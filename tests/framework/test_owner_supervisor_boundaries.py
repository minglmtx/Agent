"""Strict ABI, startup effects and diagnostics; actual original children only."""

import errno
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.processes import linux_pidfd as abi
from lab_generate_skill.adapters.processes import owner_supervisor as module
from lab_generate_skill.adapters.processes.owner_pidfd import ended
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from owner_supervisor_fixtures import owner_process
from test_slurm_commands import guard


@pytest.mark.parametrize("pid", [None, True, 0, -1, 2**31, "1", []])
def test_invalid_pid_before_syscall(pid: Any) -> None:
    with pytest.raises(ValueError):
        abi.open_pidfd(pid)


@pytest.mark.parametrize("fd", [None, True, -1, 2**31, "1", []])
def test_invalid_descriptor_before_signal(fd: Any) -> None:
    with pytest.raises(ValueError):
        abi.kill_pidfd(fd)


def test_pidfd_is_not_inheritable_and_plain_fd_cannot_signal() -> None:
    pidfd = abi.open_pidfd(os.getpid())
    ordinary = os.open("/dev/null", os.O_RDONLY)
    try:
        assert not ended(pidfd) and not os.get_inheritable(pidfd)
        with pytest.raises(OSError) as caught:
            abi.kill_pidfd(ordinary)
        assert caught.value.errno == errno.EBADF
    finally:
        os.close(ordinary)
        os.close(pidfd)


def test_unsupported_abi_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as patch:
        patch.setattr(os, "uname", lambda: SimpleNamespace(machine="aarch64"))
        with pytest.raises(RuntimeError, match="x86-64"):
            abi.open_pidfd(os.getpid())


def test_fork_failure_keeps_original_and_closes_owner_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owner_process(tmp_path) as (_, owner):
        failure = OSError("fork unavailable")

        def fail() -> int:
            raise failure

        with monkeypatch.context() as patch:
            patch.setattr(os, "fork", fail)
            before = set(os.listdir("/proc/self/fd"))
            with pytest.raises(OSError) as caught:
                module.supervise_owner(owner, guard(), lambda *args: 0)
            assert caught.value is failure
            assert set(os.listdir("/proc/self/fd")) == before


def test_child_pidfd_failure_kills_only_unreaped_owned_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owner_process(tmp_path) as (parent, owner):
        children = []
        failure = OSError("child pidfd unavailable")

        def fail(pid: int) -> int:
            children.append(pid)
            raise failure

        monkeypatch.setattr(module, "open_pidfd", fail)
        with pytest.raises(OSError) as caught:
            module.supervise_owner(owner, guard(), lambda *args: 0)
        assert caught.value is failure and len(children) == 1
        assert not Path(f"/proc/{children[0]}").exists() and parent.is_alive()


@pytest.mark.parametrize("returned", [True, -1, 256, None])
def test_invalid_child_return_is_failure_with_diagnostic(
    tmp_path: Path, returned: Any, capfd: pytest.CaptureFixture[str]
) -> None:
    with owner_process(tmp_path) as (_, owner):
        assert module.supervise_owner(owner, guard(), lambda *args: returned) == 125
        diagnostic = capfd.readouterr().err.split("GENERATOR_GUARDED_CHILD_FAILED ")[-1]
        value = json.loads(diagnostic)
        assert value["type_name"] == "ValueError" and value["frames"]


@pytest.mark.parametrize(
    "changed", ["worker", "supervisor", "host", "boot", "signal", "version"]
)
def test_guard_identity_and_signal_contract(tmp_path: Path, changed: str) -> None:
    with owner_process(tmp_path) as (_, owner):
        supervisor = owner.model_copy(update={"process_id": owner.process_id + 1000000})
        worker = owner.model_copy(update={"process_id": owner.process_id + 1000001})
        value = ProcessOwnerGuard(
            controller=owner, supervisor=supervisor, worker=worker
        ).model_dump()
        if changed in ("worker", "supervisor"):
            value[changed] = owner.model_dump()
        elif changed == "host":
            value["worker"]["node_id"] = "another"
        elif changed == "boot":
            value["worker"]["boot_id"] = "00000000-0000-0000-0000-000000000001"
        elif changed == "signal":
            value["parent_death_signal"] = "SIGTERM"
        else:
            value["schema_version"] = "old"
        with pytest.raises(ValueError):
            ProcessOwnerGuard.model_validate(value)
