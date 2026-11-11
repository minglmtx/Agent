"""Same-node independent writers and exit after claim, before CAS receipt."""

from lab_generate_skill.ports.lifecycle import OperationControl

import multiprocessing
import os
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.runtime.lifecycle import OperationGuards
from claim_fixtures import fixture, operation, UnitClaimAuthority
from test_run_journal import CancelSwitch


class ExitBeforeReceipt:
    def __init__(self, store: FileEvidenceStore) -> None:
        self.store = store

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        return self.store.read(reference, control=control)

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        if metadata.content_schema == "source-claim/1":
            os._exit(23)
        return self.store.put(data, metadata, control=control)


def worker(root: str, payload: str, gate: Any, queue: Any, crash: bool = False) -> None:
    path = Path(root)
    binding = SourceClaimBinding.model_validate_json(payload)
    store = FileEvidenceStore(path / "evidence")
    controls = OperationGuards(SystemClock(), CancelSwitch())
    ledger = FileSourceClaims(
        path / "claims",
        "unit-scope",
        controls,
        ExitBeforeReceipt(store) if crash else store,
        EvidenceRunPlans(store, controls),
        UnitClaimAuthority(),
    )
    gate.wait(10)
    try:
        receipt = ledger.claim(binding, operation(binding))
    except OwnershipConflict:
        queue.put(("conflict", binding.run.owner.worker_id))
    else:
        queue.put(("claimed", receipt.record.binding.run.owner.worker_id))


def test_two_independent_workers_claim_only_one_original_binding(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    gate = ctx.Event()
    queue = ctx.Queue()
    other = f.binding.model_copy(
        update={
            "run": f.binding.run.model_copy(
                update={
                    "owner": f.binding.run.owner.model_copy(
                        update={"worker_id": "other", "job_id": "other-job"}
                    )
                }
            )
        }
    )
    children = [
        ctx.Process(
            target=worker, args=(str(tmp_path), b.model_dump_json(), gate, queue)
        )
        for b in (f.binding, other)
    ]
    try:
        for child in children:
            child.start()
        gate.set()
        for child in children:
            child.join(20)
            assert not child.is_alive() and child.exitcode == 0
        results = [queue.get(timeout=3) for _ in children]
        assert sorted(x[0] for x in results) == ["claimed", "conflict"]
        winner = next(x[1] for x in results if x[0] == "claimed")
        record = f.ledger().read(f.binding.key, operation(f.binding))
        assert record.binding.run.owner.worker_id == winner
    finally:
        for child in children:
            if child.is_alive():
                child.kill()
                child.join(5)
        queue.close()
        queue.join_thread()


def test_new_process_recovers_original_claim_after_pre_receipt_exit(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    gate = ctx.Event()
    queue = ctx.Queue()
    child = ctx.Process(
        target=worker,
        args=(str(tmp_path), f.binding.model_dump_json(), gate, queue, True),
    )
    try:
        child.start()
        gate.set()
        child.join(20)
        assert not child.is_alive() and child.exitcode == 23
        record = f.ledger().read(f.binding.key, operation(f.binding))
        saved = f.path.read_bytes()
        receipt = f.ledger().claim(f.binding, operation(f.binding))
        assert receipt.record == record and f.path.read_bytes() == saved
        assert (
            f.ledger().require(
                receipt.reference,
                f.attempt(receipt.reference),
                operation(f.binding, attempt="attempt"),
            )
            == record
        )
    finally:
        if child.is_alive():
            child.kill()
            child.join(5)
        queue.close()
        queue.join_thread()
