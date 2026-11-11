"""Original pidfd readback only; unknown/cancelled observations retain facts."""

import os
import threading
from pathlib import Path
from typing import cast
import subprocess
import pytest
from lab_generate_skill.adapters.processes import pid_namespace as module
from lab_generate_skill.adapters.processes.pid_namespace import HeldPidNamespace
from native_quiescence_fixtures import Child, Held
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "unknown",
        "forced",
        "closed",
        "foreign_owner",
        "cancel_after_observation",
    ],
)
def test_observe_original_namespace_without_any_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    child = Child(3100)
    child.returncode = 0
    original = Held("mysql", child)
    held = HeldPidNamespace.__new__(HeldPidNamespace)
    held.owner = (os.getpid(), threading.get_ident())
    held.closed = False
    held.attempted = False
    held.stopped = None
    held.init_fd = 999
    held.launcher = cast(subprocess.Popen[bytes], child)
    held.identity = original.identity
    error = TimeoutError("original observation deadline")

    class Control:
        calls = 0

        def checkpoint(self) -> float:
            self.calls += 1
            if change == "cancel_after_observation" and self.calls == 2:
                raise error
            return 5.0

        def wait(self, seconds: float) -> None:
            raise error

    def forbidden(fd: int) -> None:
        pytest.fail("Read-only namespace observation cannot signal")

    monkeypatch.setattr(module, "kill_pidfd", forbidden)
    monkeypatch.setattr(module, "ended", lambda fd: change != "unknown")
    if change == "forced":
        held.attempted = True
    elif change == "closed":
        held.closed = True
    elif change == "foreign_owner":
        held.owner = (0, 0)
    if change == "none":
        result = held.observe_stopped(guard(5))
        assert result.original == original.identity and result.launcher_returncode == 0
    elif change in ("unknown", "cancel_after_observation"):
        with pytest.raises(TimeoutError) as caught:
            held.observe_stopped(Control())
        assert caught.value is error
        assert getattr(error, "native_namespace_identity") == original.identity
        assert (getattr(error, "native_namespace_stopped") is not None) == (
            change == "cancel_after_observation"
        )
    else:
        with pytest.raises(RuntimeError):
            held.observe_stopped(guard(5))
    assert not child.terms
