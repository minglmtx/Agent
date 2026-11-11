"""Two independent publishers on one node compete for one expected revision."""

import multiprocessing as mp
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.errors import RevisionConflict
from release_current_fixtures import store, op, switch


def publish(root: str, name: str, barrier: Any, queue: Any) -> None:
    try:
        change = switch(0, name)
        barrier.wait(timeout=20)
        result = store(Path(root)).activate(change)
        queue.put(("committed", result.active.release_id if result.active else None))
    except RevisionConflict:
        queue.put(("conflict", name))
    except BaseException as error:
        queue.put(("error", repr(error)))


def test_exactly_one_process_wins_expected_revision(tmp_path: Path) -> None:
    store(tmp_path).initialize(op())
    context = mp.get_context("spawn")
    queue = context.Queue()
    barrier = context.Barrier(2)
    workers = [
        context.Process(target=publish, args=(str(tmp_path), name, barrier, queue))
        for name in ("one", "two")
    ]
    try:
        for worker in workers:
            worker.start()
        results = [queue.get(timeout=30) for _ in workers]
        for worker in workers:
            worker.join(timeout=30)
            assert worker.exitcode == 0
        assert sorted(status for status, _ in results) == ["committed", "conflict"]
        saved = store(tmp_path).read(op("parent-read"))
        assert saved.revision == 1 and saved.active is not None
        assert ("committed", saved.active.release_id) in results
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.kill()
            if worker.pid is not None:
                worker.join(timeout=5)
        queue.close()
        queue.join_thread()
