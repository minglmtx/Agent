"""Live original-owner death, supervisor death, strict scope and cleanup faults."""

import os
import json
import multiprocessing as mp
import signal
import time
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.processes import owner_supervisor as module
from lab_generate_skill.adapters.processes import owner_pidfd as pin
from lab_generate_skill.adapters.processes.linux_pidfd import open_pidfd, kill_pidfd
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.errors import OwnershipConflict
from owner_supervisor_fixtures import owner_process, monitor_main, wait_file
from test_slurm_commands import guard


def test_actual_normal_child_guard_and_reap(tmp_path: Path) -> None:
    with owner_process(tmp_path) as (_, owner):
        path = tmp_path / "guard.json"

        def work(supervisor: ProcessIdentity, fd: int) -> int:
            receipt = module.observed_guard(owner, supervisor, fd, guard())
            path.write_text(receipt.model_dump_json())
            return 7

        assert module.supervise_owner(owner, guard(), work) == 7
        receipt = ProcessOwnerGuard.model_validate_json(path.read_bytes())
        assert (
            receipt.controller == owner and receipt.supervisor.process_id == os.getpid()
        )
        assert not Path(f"/proc/{receipt.worker.process_id}").exists()


@pytest.mark.parametrize("victim", ["controller", "supervisor"])
def test_independent_guard_stops_gil_blocked_model(tmp_path: Path, victim: str) -> None:
    with owner_process(tmp_path) as (owner_process_handle, owner):
        output = tmp_path / "guard.json"
        process = mp.get_context("fork").Process(
            target=monitor_main, args=(owner, output)
        )
        process.start()
        fd = None
        try:
            receipt = ProcessOwnerGuard.model_validate_json(wait_file(output))
            assert receipt.supervisor.process_id == process.pid
            fd = open_pidfd(receipt.worker.process_id)
            assert not pin.ended(fd)
            until = time.monotonic() + 5
            syscall = ""
            while time.monotonic() < until:
                syscall = Path(f"/proc/{receipt.worker.process_id}/syscall").read_text()
                if syscall.split()[0] == "34":  # Linux x86-64 pause, PyDLL holds GIL.
                    break
                time.sleep(0.01)
            assert (
                syscall.split()[0] == "34"
            ), "Worker never entered native blocking call"
            output_root = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
            if output_root:
                (Path(output_root) / f"owner-supervision-{victim}.json").write_text(
                    json.dumps(
                        {"guard": receipt.model_dump(mode="json"), "syscall": syscall}
                    )
                    + "\n"
                )
            if victim == "controller":
                owner_process_handle.kill()
                owner_process_handle.join(5)
            else:
                process.kill()
            until = time.monotonic() + 5
            while not pin.ended(fd) and time.monotonic() < until:
                time.sleep(0.01)
            assert pin.ended(fd), "Original worker survived its owner/supervisor"
            process.join(5)
            assert not process.is_alive()
            if victim == "controller":
                assert output.with_suffix(".error").read_text() == "OwnershipConflict"
            else:
                assert process.exitcode == -signal.SIGKILL
        finally:
            if fd is not None:
                if not pin.ended(fd):
                    kill_pidfd(fd)
                os.close(fd)
            if process.is_alive():
                process.kill()
            process.join(5)
            process.close()


@pytest.mark.parametrize("field", ["start_ticks", "boot_id", "node_id"])
def test_wrong_original_incarnation_never_forks(
    tmp_path: Path, field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owner_process(tmp_path) as (_, owner):
        value: Any = {
            "start_ticks": owner.start_ticks + 1,
            "boot_id": "00000000-0000-0000-0000-000000000001",
            "node_id": "other",
        }[field]

        def forbidden() -> int:
            pytest.fail("fork after wrong owner")

        monkeypatch.setattr(os, "fork", forbidden)
        with pytest.raises(OwnershipConflict):
            module.supervise_owner(
                owner.model_copy(update={field: value}), guard(), lambda *args: 0
            )


def test_already_ended_owner_never_forks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owner_process(tmp_path) as (process, owner):
        process.kill()
        process.join(5)

        def forbidden() -> int:
            pytest.fail("fork after ended owner")

        monkeypatch.setattr(os, "fork", forbidden)
        with pytest.raises(FileNotFoundError):
            module.supervise_owner(owner, guard(), lambda *args: 0)


def test_parent_dies_before_guard_arm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_prctl", lambda *args: None)
    monkeypatch.setattr(os, "getppid", lambda: 1)
    with pytest.raises(OwnershipConflict):
        module.arm_parent_death(999999)


@pytest.mark.parametrize("value", [None, True, 0, -1, "12", [], {}])
def test_invalid_parent_identity(value: Any) -> None:
    with pytest.raises(ValueError):
        module.arm_parent_death(value)


def test_fd_cleanup_preserves_primary_and_all_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = ValueError("original")
    calls = []

    def fail(fd: int) -> None:
        calls.append(fd)
        raise OSError(str(fd))

    monkeypatch.setattr(os, "close", fail)
    with pytest.raises(BaseExceptionGroup) as caught:
        pin.close_owned([3, 4], primary)
    assert caught.value.exceptions[0] is primary
    assert len(caught.value.exceptions) == 3 and calls == [4, 3]


@pytest.mark.parametrize("value", [None, {}, [], {"controller": None}])
def test_invalid_guard_envelope(value: Any) -> None:
    with pytest.raises(ValidationError):
        ProcessOwnerGuard.model_validate(value)
