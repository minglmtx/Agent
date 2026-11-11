"""Main-thread guard and owned relay threads; isolated actual kernel check below."""

from concurrent.futures import ThreadPoolExecutor
import ctypes
import json
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.storage_guard import (
    OriginalBrowserProcessGuard,
)
import lab_generate_skill.adapters.browsergym.storage_guard as module
from lab_generate_skill.adapters.processes.owner_supervisor import supervise_owner
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.process_identity import ProcessIdentity
from owner_supervisor_fixtures import owner_process
from generator_worker_fixtures import unit_guard
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault", ["none", "unobserved", "controller-ended", "parent", "worker", "fork"]
)
def test_owned_thread_live_delegation(
    fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.adapters.processes.worker_identity import (
        current_process_identity,
    )

    controller = current_process_identity()
    original = unit_guard(controller, guard())
    value = OriginalBrowserProcessGuard(controller, original.supervisor, 123)
    monkeypatch.setattr(module, "observed_guard", lambda *args: original)
    monkeypatch.setattr(module, "ended", lambda fd: fault == "controller-ended")
    monkeypatch.setattr(
        os,
        "getppid",
        lambda: original.supervisor.process_id + (1 if fault == "parent" else 0),
    )
    monkeypatch.setattr(
        module,
        "current_process_identity",
        lambda: (
            original.worker.model_copy(update={"start_ticks": 999})
            if fault == "worker"
            else original.worker
        ),
    )
    if fault != "unobserved":
        assert value.observe(guard()) == original
    if fault == "fork":
        value.owner = (value.owner[0] + 1, value.owner[1])
    with ThreadPoolExecutor(max_workers=1) as pool:
        if fault == "none":
            assert pool.submit(value.observe, guard()).result() == original
        else:
            with pytest.raises(OwnershipConflict):
                pool.submit(value.observe, guard()).result()


@pytest.mark.parametrize("fd", [None, True, -1, "1"])
def test_invalid_fd_and_non_owner_constructor_rejected(fd: Any) -> None:
    from lab_generate_skill.adapters.processes.worker_identity import (
        current_process_identity,
    )

    identity = current_process_identity()
    with pytest.raises(ValueError):
        OriginalBrowserProcessGuard(identity, identity, fd)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(OriginalBrowserProcessGuard, identity, identity, 1).result()


def test_actual_guarded_process_threads_keep_original_owner(tmp_path: Path) -> None:
    output = tmp_path / "threaded-original-guard.json"
    with owner_process(tmp_path) as (_, controller):

        def work(supervisor: ProcessIdentity, fd: int) -> int:
            access = OriginalBrowserProcessGuard(controller, supervisor, fd)
            original = access.observe(guard())

            def collect() -> dict[str, Any]:
                signal = ctypes.c_int()
                assert ctypes.CDLL(None).prctl(2, ctypes.byref(signal), 0, 0, 0) == 0
                observed = access.observe(guard())
                assert observed == original
                return {
                    "thread_parent_death_signal": signal.value,
                    "original": observed.model_dump(mode="json"),
                }

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: collect(), range(4)))
            output.write_text(
                json.dumps(
                    {"original": original.model_dump(mode="json"), "threads": results}
                )
            )
            return 0

        assert supervise_owner(controller, guard(), work) == 0
    data = json.loads(output.read_text())
    assert len(data["threads"]) == 4
    assert {entry["thread_parent_death_signal"] for entry in data["threads"]} == {0}
    assert not Path(f'/proc/{data["original"]["worker"]["process_id"]}').exists()
    root = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
    if root:
        (Path(root) / output.name).write_bytes(output.read_bytes())
