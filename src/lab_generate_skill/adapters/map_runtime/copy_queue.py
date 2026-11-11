"""Two file writers inside the original Map worker; owner polling stays serial.

No resource acquisition, ledger, subprocess, retry or readiness publication.
Failure stops submission and cooperatively stops both writers before return.
Blocking native I/O retains the existing outer fixed-worker supervision boundary.
"""

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, Future, wait, FIRST_COMPLETED
from dataclasses import dataclass
import math
import threading
import time
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl


@dataclass(frozen=True)
class CopyWork:
    copy: Callable[[OperationControl], None]
    size_bytes: int


@dataclass(frozen=True)
class CopiedFiles:
    files: int
    size_bytes: int
    peak_in_flight: int


class _Copies:
    def __init__(self, expires: float) -> None:
        self.expires = expires
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.errors: list[BaseException] = []

    def fail(self, error: BaseException) -> None:
        with self.lock:
            if not any(known is error for known in self.errors):
                self.errors.append(error)
            self.stopped.set()

    def checkpoint(self) -> float:
        if self.stopped.is_set():
            raise OperationStopped("CANCELLED", "map-file-copy")
        remaining = self.expires - time.monotonic()
        if remaining <= 0:
            raise OperationStopped("DEADLINE_EXCEEDED", "map-file-copy")
        return remaining

    def wait(self, seconds: float) -> None:
        if (
            type(seconds) not in (int, float)
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("Bounded copy wait required")
        self.stopped.wait(min(seconds, self.checkpoint()))
        self.checkpoint()


def copy_files(work: Iterable[CopyWork], control: OperationControl) -> CopiedFiles:
    # The caller may enforce thread ownership; it is never called by a writer.
    remaining = control.checkpoint()
    if (
        type(remaining) not in (int, float)
        or not math.isfinite(remaining)
        or remaining <= 0
    ):
        raise ValueError("Positive finite original copy window required")
    state = _Copies(time.monotonic() + remaining)
    pending: dict[Future[None], CopyWork] = {}
    iterator = iter(work)
    exhausted = False
    count = size = peak = 0
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="map-file-copy")

    def run(item: CopyWork) -> None:
        try:
            state.checkpoint()
            item.copy(state)
            state.checkpoint()
        except BaseException as error:
            state.fail(error)
            raise

    try:
        while pending or not exhausted:
            if not state.stopped.is_set():
                try:
                    control.checkpoint()
                    while len(pending) < 2 and not exhausted:
                        # A failed writer and submission share this lock, so no
                        # further file is claimed after failure is registered.
                        with state.lock:
                            if state.stopped.is_set():
                                break
                            try:
                                item = next(iterator)
                            except StopIteration:
                                exhausted = True
                                break
                            if (
                                not isinstance(item, CopyWork)
                                or type(item.size_bytes) is not int
                                or item.size_bytes < 0
                                or not callable(item.copy)
                            ):
                                raise TypeError("Exact bounded Map file work required")
                            pending[pool.submit(run, item)] = item
                            peak = max(peak, len(pending))
                except BaseException as error:
                    state.fail(error)
            if not pending:
                break
            done, _ = wait(pending, timeout=0.05, return_when=FIRST_COMPLETED)
            for future in done:
                item = pending.pop(future)
                try:
                    future.result()
                except BaseException as error:
                    # Normally registered by run; also retain executor failures
                    # which occur before run (and do not issue a ready result).
                    state.fail(error)
                else:
                    count += 1
                    size += item.size_bytes
    except BaseException as error:
        state.fail(error)
    finally:
        state.stopped.set()
        pool.shutdown(wait=True, cancel_futures=True)
    if len(state.errors) == 1:
        raise state.errors[0]
    if state.errors:
        raise BaseExceptionGroup(
            "Map file copy failed; all writers stopped", state.errors
        )
    control.checkpoint()
    return CopiedFiles(count, size, peak)
