"""Owned namespace identity and actual PID1 closure, never site restoration proof."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.namespace_observation import parse_child
from lab_generate_skill.adapters.processes.pid_namespace import HeldPidNamespace
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.linux_pidfd import open_pidfd
from lab_generate_skill.adapters.processes.owner_pidfd import ended
from lab_generate_skill.domain.native_namespace import NativeNamespaceStopped
from test_admin_database_native import IMAGE
from test_slurm_commands import guard


def child_input() -> tuple[bytes, bytes]:
    uid = os.getuid()
    status = f"Pid: 42\nTgid: 42\nPPid: {os.getpid()}\nUid: {uid} {uid} {uid} {uid}\nNSpid: 42 1\nNStgid: 42 1\n".encode()
    stat = (
        "42 (nested ) child) S "
        + str(os.getpid())
        + " "
        + " ".join(["0"] * 17)
        + " 123 0"
    ).encode()
    return status, stat


def test_namespace_init_identity_is_not_host_pid() -> None:
    status, stat = child_input()
    result = parse_child(status, stat, 42, os.getuid(), current_process_identity())
    assert result.namespace_pids == (42, 1) and result.identity.start_ticks == 123


@pytest.mark.parametrize(
    "change",
    [
        "empty",
        "duplicate",
        "foreign_uid",
        "foreign_parent",
        "thread",
        "wrong_pid",
        "nested",
        "zero",
        "missing",
        "stat",
    ],
)
def test_invalid_namespace_identity_rejected(change: str) -> None:
    status, stat = child_input()
    if change == "empty":
        status = b""
    elif change == "duplicate":
        status += b"Pid: 42\n"
    elif change == "foreign_uid":
        status = status.replace(f"Uid: {os.getuid()}".encode(), b"Uid: 0")
    elif change == "foreign_parent":
        status = status.replace(f"PPid: {os.getpid()}".encode(), b"PPid: 1")
    elif change == "thread":
        status = status.replace(b"Tgid: 42", b"Tgid: 43")
    elif change == "wrong_pid":
        status = status.replace(b"NSpid: 42", b"NSpid: 43")
    elif change == "nested":
        status = status.replace(b"42 1", b"42 2 1")
    elif change == "zero":
        status = status.replace(b"42 1", b"42 0")
    elif change == "missing":
        status = status.replace(b"NSpid: 42 1\n", b"")
    else:
        stat = b"bad"
    with pytest.raises(ValueError):
        parse_child(status, stat, 42, os.getuid(), current_process_identity())


def test_host_child_cannot_be_used_as_container_init(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with pytest.raises(ValueError, match="Exactly one"):
            HeldPidNamespace("php", process, guard(5))
        assert process.poll() is None
    finally:
        process.kill()
        process.wait(timeout=5)


def test_actual_container_original_init_stops_detached_descendants(
    tmp_path: Path,
) -> None:
    assert os.environ.get("SLURM_JOB_ID")
    log = tmp_path / "container.log"
    held = None
    pins: list[int] = []
    canary = subprocess.Popen(
        ["/bin/sleep", "60"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    child = None
    try:
        with log.open("wb") as output:
            child = subprocess.Popen(
                [
                    "/usr/bin/apptainer",
                    "exec",
                    "--cleanenv",
                    "--containall",
                    "--no-home",
                    "--no-mount",
                    "bind-paths,hostfs,cwd",
                    "--pwd",
                    "/",
                    str(IMAGE),
                    "sh",
                    "-ec",
                    "setsid sh -c 'trap \"\" TERM; sleep 60 & wait' & echo ready; wait",
                ],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            )
            control = guard(15)
            while b"ready" not in log.read_bytes():
                assert child.poll() is None, log.read_text()
                control.wait(0.05)
            held = HeldPidNamespace("php", child, control)
            # Pin original namespace descendants independently before killing init.
            root = held.identity.init.process_id
            queue = [root]
            while queue:
                pid = queue.pop(0)
                pins.append(open_pidfd(pid))
                queue.extend(
                    int(v)
                    for v in (Path("/proc") / str(pid) / "task" / str(pid) / "children")
                    .read_text()
                    .split()
                )
                assert len(pins) <= 20
            assert len(pins) >= 3
            facts = held.stop(guard(10))
            assert all(ended(fd) for fd in pins) and child.poll() is not None
            assert canary.poll() is None
            assert held.stop(guard(5)) == facts
            for value in (False, 0, 1, "true", None):
                with pytest.raises(ValueError):
                    NativeNamespaceStopped.model_validate(
                        {**facts.model_dump(), "init_exit_observed": value}
                    )
            (
                Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "native-namespace.json"
            ).write_text(
                json.dumps(
                    dict(
                        passed=True,
                        stopped=facts.model_dump(mode="json"),
                        held_descendants=len(pins),
                        unrelated_canary_alive=True,
                    ),
                    indent=2,
                )
                + "\n"
            )
            held.close()
            held.close()
            with pytest.raises(RuntimeError):
                held.stop(guard(5))
    finally:
        if held is not None:
            held.close()
        for fd in pins:
            os.close(fd)
        for process in (child, canary):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=10)


@pytest.mark.parametrize(
    "mapping", ["exact", "root", "range", "different", "group", "nested"]
)
def test_launcher_private_user_namespace_is_exact_owner_only(mapping: str) -> None:
    from lab_generate_skill.adapters.processes.namespace_observation import (
        parse_launcher,
    )

    status, stat = child_input()
    status = status.replace(b"42 1", b"42")
    uid, gid = os.getuid(), os.getgid()
    users = f"{uid} {uid} 1".encode()
    groups = f"{gid} {gid} 1".encode()
    if mapping == "root":
        users = f"0 {uid} 1".encode()
    elif mapping == "range":
        users = f"{uid} {uid} 2".encode()
    elif mapping == "different":
        users = f"{uid} {uid + 1} 1".encode()
    elif mapping == "group":
        groups = f"{gid} {gid + 1} 1".encode()
    elif mapping == "nested":
        status = status.replace(b"NSpid: 42\n", b"NSpid: 42 1\n").replace(
            b"NStgid: 42\n", b"NStgid: 42 1\n"
        )
    if mapping == "exact":
        assert (
            parse_launcher(
                status, stat, users, groups, 42, uid, gid, current_process_identity()
            ).process_id
            == 42
        )
    else:
        with pytest.raises(ValueError):
            parse_launcher(
                status, stat, users, groups, 42, uid, gid, current_process_identity()
            )


@pytest.mark.parametrize("failure", ["cancel", "kill", "late", "owner", "close"])
def test_native_stop_boundaries_keep_original_handle_and_no_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    import lab_generate_skill.adapters.processes.pid_namespace as implementation
    from lab_generate_skill.adapters.processes.linux_pidfd import kill_pidfd

    from lab_generate_skill.adapters.processes.owner_pidfd import close_owned

    original_close = close_owned
    log = tmp_path / "fault-container.log"
    held = None
    process = None
    saved_owner = None
    try:
        with log.open("wb") as output:
            process = subprocess.Popen(
                [
                    "/usr/bin/apptainer",
                    "exec",
                    "--cleanenv",
                    "--containall",
                    "--no-home",
                    "--no-mount",
                    "bind-paths,hostfs,cwd",
                    "--pwd",
                    "/",
                    str(IMAGE),
                    "sh",
                    "-ec",
                    "echo ready; sleep 60",
                ],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            )
            control = guard(15)
            while b"ready" not in log.read_bytes():
                assert process.poll() is None, log.read_text()
                control.wait(0.05)
            held = HeldPidNamespace("nginx", process, control)
            saved_owner = held.owner
            if failure == "cancel":

                class Cancel:
                    def checkpoint(self) -> float:
                        raise TimeoutError("cancel before stop")

                    def wait(self, seconds: float) -> None:
                        self.checkpoint()

                with pytest.raises(TimeoutError):
                    held.stop(Cancel())
                assert not held.attempted and not ended(held.init_fd)
            elif failure == "kill":
                calls: list[int] = []

                def failed_kill(fd: int) -> None:
                    calls.append(fd)
                    raise OSError("original pidfd signal failed")

                with monkeypatch.context() as patch:
                    patch.setattr(implementation, "kill_pidfd", failed_kill)
                    with pytest.raises(OSError) as caught:
                        held.stop(guard(5))
                    assert (
                        getattr(caught.value, "native_namespace_identity")
                        == held.identity
                    )
                    with pytest.raises(RuntimeError):
                        held.stop(guard(5))
                assert calls == [held.init_fd] and not ended(held.init_fd)
            elif failure == "late":

                class Late:
                    def checkpoint(self) -> float:
                        if held is not None and held.stopped is not None:
                            raise TimeoutError("after observed exit")
                        return 5.0

                    def wait(self, seconds: float) -> None:
                        time.sleep(seconds)

                with pytest.raises(TimeoutError) as caught:
                    held.stop(Late())
                assert (
                    held.stopped is not None
                    and getattr(caught.value, "native_namespace_stopped")
                    == held.stopped
                )
                assert held.stop(guard(5)) == held.stopped
            elif failure == "owner":
                held.owner = (os.getpid(), saved_owner[1] + 1)
                with pytest.raises(RuntimeError):
                    held.stop(guard(5))
                held.owner = saved_owner
                assert not ended(held.init_fd)
            else:
                held.stop(guard(5))
                calls_close: list[int] = []

                def close_error(
                    fds: list[int], primary: BaseException | None = None
                ) -> None:
                    calls_close.append(len(fds))
                    original_close(fds, primary)
                    raise OSError("after descriptor close")

                with monkeypatch.context() as patch:
                    patch.setattr(implementation, "close_owned", close_error)
                    with pytest.raises(OSError):
                        held.close()
                    held.close()
                assert calls_close == [3] and held.closed and not held.fds
    finally:
        if held is not None:
            if saved_owner is not None:
                held.owner = saved_owner
            if not held.closed and not ended(held.init_fd):
                kill_pidfd(held.init_fd)
            if process is not None:
                process.wait(timeout=10)
            held.close()
        elif process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
