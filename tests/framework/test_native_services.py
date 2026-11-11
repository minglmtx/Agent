"""Actual original child masters; logs, exact-once starts and cleanup facts."""

from pathlib import Path
import sys
import time
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from test_slurm_commands import guard


def test_real_services_stop_repeatedly_without_relaunch_or_secret_inheritance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    services = LocalNativeServices(tmp_path)
    services.start(
        "first",
        (
            sys.executable,
            "-u",
            "-c",
            "import os,time; assert 'OPENROUTER_API_KEY' not in os.environ; print('ready'); time.sleep(60)",
        ),
        guard(),
    )
    deadline = time.monotonic() + 5
    while b"ready" not in (tmp_path / "first.log").read_bytes():
        assert time.monotonic() < deadline
        time.sleep(0.01)
    services.require_running()
    with pytest.raises(RuntimeError):
        services.start("first", (sys.executable, "-c", "pass"), guard())
    facts = services.stop(guard())
    assert len(facts) == 1 and facts[0].state == "reaped" and facts[0].returncode == -15
    assert services.stop(guard()) == facts
    with pytest.raises(RuntimeError):
        services.start("other", (sys.executable, "-c", "pass"), guard())


def test_ignoring_term_uses_bounded_kill(tmp_path: Path) -> None:
    services = LocalNativeServices(tmp_path)
    services.start(
        "ignore",
        (
            sys.executable,
            "-u",
            "-c",
            "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready'); time.sleep(60)",
        ),
        guard(),
    )
    ready = guard()
    while b"ready" not in (tmp_path / "ignore.log").read_bytes():
        ready.wait(0.01)
    facts = services.stop(guard(2))
    assert (
        facts[0].state == "reaped"
        and facts[0].returncode == -9
        and facts[0].kill_requested
    )


@pytest.mark.parametrize(
    "name,args",
    [
        ("../escape", ("/bin/true",)),
        ("", ("/bin/true",)),
        ("valid", ()),
        ("valid", ("relative",)),
        ("valid", ["/bin/true"]),
        ("valid", ("/bin/true", None)),
    ],
)
def test_invalid_start_no_log_or_child(tmp_path: Path, name: str, args: Any) -> None:
    services = LocalNativeServices(tmp_path)
    with pytest.raises(ValueError):
        services.start(name, args, guard())
    assert services.children == {} and list(tmp_path.iterdir()) == []


def test_failed_spawn_stays_attempted_and_closes_log(tmp_path: Path) -> None:
    services = LocalNativeServices(tmp_path)
    with pytest.raises(FileNotFoundError):
        services.start("failed", ("/no/such/executable",), guard())
    with pytest.raises(RuntimeError):
        services.start("failed", ("/bin/true",), guard())
    assert services.stop(guard()) == ()


def test_exited_master_is_not_healthy(tmp_path: Path) -> None:
    services = LocalNativeServices(tmp_path)
    services.start("exit", (sys.executable, "-c", "raise SystemExit(7)"), guard())
    child = services.children["exit"]
    child.wait(timeout=5)
    with pytest.raises(RuntimeError, match="exited"):
        services.require_running()
    facts = services.stop(guard())
    assert facts[0].returncode == 7 and not facts[0].kill_requested


def test_cancellation_after_spawn_keeps_original_handle_for_cleanup(
    tmp_path: Path,
) -> None:
    services = LocalNativeServices(tmp_path)
    first = RuntimeError("cancel after spawn")

    class Control:
        calls = 0

        def checkpoint(self) -> float:
            self.calls += 1
            if self.calls > 1:
                raise first
            return 5.0

        def wait(self, seconds: float) -> None:
            raise AssertionError("unused")

    with pytest.raises(RuntimeError) as caught:
        services.start(
            "original", (sys.executable, "-c", "import time;time.sleep(60)"), Control()
        )
    assert caught.value is first and "original" in services.children
    facts = services.stop(guard())
    assert len(facts) == 1 and facts[0].state == "reaped"


def test_original_owner_thread_required(tmp_path: Path) -> None:
    import threading

    services = LocalNativeServices(tmp_path)
    errors: list[BaseException] = []

    def other() -> None:
        try:
            services.start("wrong", (sys.executable, "-c", "pass"), guard())
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=other)
    thread.start()
    thread.join(timeout=5)
    assert (
        not thread.is_alive()
        and len(errors) == 1
        and isinstance(errors[0], RuntimeError)
    )
    assert services.children == {} and list(tmp_path.iterdir()) == []
