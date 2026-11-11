"""Actual disposable child processes; every PID is created by this test tree."""

import ctypes
import multiprocessing as mp
from multiprocessing.process import BaseProcess
import time
from pathlib import Path
from collections.abc import Iterator
from contextlib import contextmanager
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.owner_supervisor import (
    supervise_owner,
    observed_guard,
)
from lab_generate_skill.domain.process_identity import ProcessIdentity
from test_slurm_commands import guard


def owner_main(path: Path) -> None:
    staging = path.with_suffix(".tmp")
    staging.write_text(current_process_identity().model_dump_json())
    staging.replace(path)
    time.sleep(60)


def wait_file(path: Path) -> bytes:
    until = time.monotonic() + 10
    while time.monotonic() < until:
        if path.exists():
            value = path.read_bytes()
            if value:
                return value
        time.sleep(0.01)
    raise TimeoutError("Test process did not produce its handshake")


@contextmanager
def owner_process(root: Path) -> Iterator[tuple[BaseProcess, ProcessIdentity]]:
    path = root / "owner.json"
    process = mp.get_context("fork").Process(target=owner_main, args=(path,))
    process.start()
    try:
        identity = ProcessIdentity.model_validate_json(wait_file(path))
        yield process, identity
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        assert not process.is_alive()
        process.close()


def monitor_main(owner: ProcessIdentity, output: Path) -> None:
    def work(supervisor: ProcessIdentity, fd: int) -> int:
        receipt = observed_guard(owner, supervisor, fd, guard())
        staging = output.with_suffix(".tmp")
        staging.write_text(receipt.model_dump_json())
        staging.replace(output)
        # PyDLL keeps the GIL. A Python watchdog thread could not run here.
        ctypes.PyDLL(None).pause()
        return 0

    try:
        supervise_owner(owner, guard(), work)
    except BaseException as error:
        output.with_suffix(".error").write_text(type(error).__name__)
