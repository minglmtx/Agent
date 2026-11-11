"""Real independent senders sharing one ledger; file output simulates a provider.

These prove adapter call count and durable replay refusal, not a real provider's
internal retry policy, production authority or cross-node recovery capability.
"""

import multiprocessing
import os
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import ModelSendPlan, ResolvedModelRequest
from lab_generate_skill.domain.model_response import ModelSendUnconfirmed, ProviderReply
from model_sender_fixtures import Transport, send_fixture, sender


class FileTransport(Transport):
    def __init__(self, root: Path, crash: bool) -> None:
        super().__init__()
        self.root, self.crash = root, crash

    def send(
        self, request: ResolvedModelRequest, op: OperationContext
    ) -> ProviderReply:
        with (self.root / "unit-provider-calls").open("a") as file:
            file.write(request.request.request_id + "\n")
            file.flush()
            os.fsync(file.fileno())
        if self.crash:
            os._exit(19)
        return super().send(request, op)


def worker(root: str, plan_json: str, queue: Any, crash: bool = False) -> None:
    path, plan = Path(root), ModelSendPlan.model_validate_json(plan_json)
    try:
        sender(path, plan, FileTransport(path, crash)).generate(plan)
    except ModelSendUnconfirmed as error:
        if not isinstance(error.__cause__, DispatchAlreadyCommitted):
            raise
        queue.put("already_committed")
    else:
        queue.put("completed")


def test_two_processes_share_one_actual_sender_invocation(tmp_path: Path) -> None:
    f = send_fixture(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    processes = [
        ctx.Process(
            target=worker, args=(str(tmp_path), f.plan.model_dump_json(), queue)
        )
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(20)
            assert not process.is_alive() and process.exitcode == 0
        assert sorted(queue.get(timeout=3) for _ in processes) == [
            "already_committed",
            "completed",
        ]
        assert (
            tmp_path / "unit-provider-calls"
        ).read_text() == f.plan.reservation.request.request_id + "\n"
        assert f.ledger.read(f.plan.reservation.request, f.cleanup()).charged.units == 2
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
                process.join(5)
        queue.close()
        queue.join_thread()


def test_process_dies_after_send_fresh_process_cannot_retry(tmp_path: Path) -> None:
    f = send_fixture(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    processes = []
    try:
        for crash in (True, False):
            process = ctx.Process(
                target=worker,
                args=(str(tmp_path), f.plan.model_dump_json(), queue, crash),
            )
            processes.append(process)
            process.start()
            process.join(20)
            assert not process.is_alive() and process.exitcode == (19 if crash else 0)
        assert queue.get(timeout=3) == "already_committed"
        assert (
            tmp_path / "unit-provider-calls"
        ).read_text() == f.plan.reservation.request.request_id + "\n"
        record = f.ledger.read(f.plan.reservation.request, f.cleanup())
        assert record.state == "dispatching" and record.held.units == 4
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
                process.join(5)
        queue.close()
        queue.join_thread()
