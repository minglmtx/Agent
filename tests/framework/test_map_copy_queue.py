"""Bounded file concurrency and cooperative stop, real temporary partial files."""

from pathlib import Path
from functools import partial
import threading
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime.copy_queue import CopyWork, copy_files
from lab_generate_skill.ports.lifecycle import OperationControl
from test_slurm_commands import guard


def leaves(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for nested in error.exceptions for leaf in leaves(nested)]
    return [error]


@pytest.mark.parametrize("failure", ["none", "file", "cancel"])
def test_two_total_in_flight_stop_claims_and_join_before_return(
    tmp_path: Path,
    failure: str,
) -> None:
    owner = threading.get_ident()
    lock = threading.Lock()
    ready = threading.Barrier(2, timeout=5)
    first_two = threading.Event()
    active = peak = started = 0
    closed: list[int] = []
    primary = OSError("first actual copy failure")
    cancelled = TimeoutError("original owner cancellation")

    def action(index: int, control: OperationControl) -> None:
        nonlocal active, peak, started
        with lock:
            active += 1
            started += 1
            peak = max(peak, active)
            if started == 2:
                first_two.set()
        try:
            with (tmp_path / str(index)).open("xb") as stream:
                stream.write(b"partial")
                if index < 2:
                    ready.wait()
                    if failure == "file" and index == 0:
                        raise primary
                    if failure != "none":
                        while True:
                            control.wait(0.001)
                control.checkpoint()
                stream.write(b" complete")
        finally:
            with lock:
                active -= 1
                closed.append(index)

    bounded = guard()

    class OwnerControl:
        def checkpoint(self) -> float:
            assert threading.get_ident() == owner
            if failure == "cancel" and first_two.is_set():
                raise cancelled
            return bounded.checkpoint()

        def wait(self, seconds: float) -> None:
            assert threading.get_ident() == owner
            bounded.wait(seconds)

    work = (CopyWork(partial(action, i), 8) for i in range(12))
    if failure == "none":
        result = copy_files(work, OwnerControl())
        assert (result.files, result.size_bytes, result.peak_in_flight) == (12, 96, 2)
        assert started == 12
    else:
        with pytest.raises(BaseException) as caught:
            copy_files(work, OwnerControl())
        assert leaves(caught.value)[0] is (primary if failure == "file" else cancelled)
        assert started == 2 and len(list(tmp_path.iterdir())) == 2
    assert active == 0 and peak == 2 and len(closed) == started
    assert not any(t.name.startswith("map-file-copy") for t in threading.enumerate())


@pytest.mark.parametrize("work", [[], [None]])
def test_empty_or_invalid_queue_never_starts_unowned_work(work: Any) -> None:
    if work:
        with pytest.raises(TypeError):
            copy_files(work, guard())
    else:
        result = copy_files(work, guard())
        assert result.files == result.size_bytes == result.peak_in_flight == 0
    assert not any(t.name.startswith("map-file-copy") for t in threading.enumerate())


def test_executor_failure_before_action_is_retained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import Future
    import lab_generate_skill.adapters.map_runtime.copy_queue as module

    failure = RuntimeError("executor failed before copy function")

    class FailedExecutor:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def submit(self, *args: Any) -> Future[None]:
            future: Future[None] = Future()
            future.set_exception(failure)
            return future

        def shutdown(self, **kwargs: Any) -> None:
            pass

    monkeypatch.setattr(module, "ThreadPoolExecutor", FailedExecutor)

    def forbidden(control: OperationControl) -> None:
        pytest.fail("Failed executor dispatched work")

    with pytest.raises(RuntimeError) as caught:
        copy_files([CopyWork(forbidden, 1)], guard())
    assert caught.value is failure
