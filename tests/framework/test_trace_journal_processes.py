"""Independent process reopen/competition; a file marker stands for a unit effect."""

import multiprocessing
import os
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.trace_journal import FileTraceJournal
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from lab_generate_skill.domain.trace_journal import TRACE_EVENT
from lab_generate_skill.domain.trace_plan import TracePlan
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_run_journal import command, CancelSwitch
from trace_journal_fixtures import UnitLiveTraceAuthority, fixture


def worker(
    root: str, plan_json: str, event_json: str, queue: Any, crash: bool = False
) -> None:
    path = Path(root)
    store = FileEvidenceStore(path / "evidence")
    plan = TracePlan.model_validate_json(plan_json)
    event = TRACE_EVENT.validate_json(event_json)
    journal = FileTraceJournal(
        path / "journal",
        plan,
        OperationGuards(SystemClock(), CancelSwitch()),
        store,
        UnitLiveTraceAuthority(store),
    )
    try:
        journal.append(event, 0, event.operation)
    except DispatchAlreadyCommitted:
        queue.put("already_committed")
        return
    if crash:
        os._exit(17)
    with (path / "unit-effect").open("a") as f:
        f.write("one effect\n")
    queue.put("accepted")


def test_two_processes_acknowledge_one_intent_and_one_unit_effect(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    data.journal().create(data.plan, command("create", attempt="attempt"))
    event = data.events()[0]
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    processes = [
        ctx.Process(
            target=worker,
            args=(
                str(tmp_path),
                data.plan.model_dump_json(),
                event.model_dump_json(),
                queue,
            ),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        if process.is_alive():
            process.kill()
            process.join()
            raise AssertionError("trace worker exceeded deadline")
        assert process.exitcode == 0
    assert sorted(queue.get(timeout=3) for _ in processes) == [
        "accepted",
        "already_committed",
    ]
    assert (tmp_path / "unit-effect").read_text() == "one effect\n"
    assert data.journal().read(command()).revision == 1
    queue.close()
    queue.join_thread()


def test_fresh_process_after_writer_exit_cannot_repeat_pending_dispatch(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    data.journal().create(data.plan, command("create", attempt="attempt"))
    event = data.events()[0]
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    args = (str(tmp_path), data.plan.model_dump_json(), event.model_dump_json(), queue)
    original = ctx.Process(target=worker, args=(*args, True))
    original.start()
    original.join(20)
    if original.is_alive():
        original.kill()
        original.join()
        raise AssertionError("original worker exceeded deadline")
    assert original.exitcode == 17
    current = data.journal().read(command())
    assert (
        current.project().intent is not None and not (tmp_path / "unit-effect").exists()
    )
    resumed = ctx.Process(target=worker, args=args)
    resumed.start()
    resumed.join(20)
    if resumed.is_alive():
        resumed.kill()
        resumed.join()
        raise AssertionError("replacement worker exceeded deadline")
    assert resumed.exitcode == 0 and queue.get(timeout=3) == "already_committed"
    assert not (tmp_path / "unit-effect").exists()
    assert data.journal().read(command()) == current
    queue.close()
    queue.join_thread()
