"""Original installed graph proof: stale facts, stop and reply boundaries."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Literal
import pytest
from closed_source_read_fixtures import actual_read_case
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadFailure,
)
from lab_generate_skill.adapters.plans.closed_source_protocol import (
    ClosedSourceReadReply,
)
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.task_bindings import TaskBindingEvidenceReader
from lab_generate_skill.adapters.processes.capture import CommandCapture
from lab_generate_skill.bootstrap.owner_metadata_store import owner_metadata_store
from lab_generate_skill.domain.closed_source_read import ClosedSourceBindingInput
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from source_review_records import ReadOnlyEvidence
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from test_slurm_commands import guard


@pytest.mark.parametrize("fault", ["none", "private", "baseline", "public"])
def test_actual_full_binding_proof_rechecks_all_original_bytes(
    tmp_path: Path, installed_sources: InstalledFixture, fault: str
) -> None:
    c = actual_read_case(tmp_path, installed_sources)
    m = c.material
    store = ReadOnlyEvidence(Path(c.scope.config.evidence_root))
    control = guard(60)
    ctx = PublicContextReceipt.model_validate_json(store.read(m.context_ref, control))
    baseline = BaselineReceipt.model_validate_json(
        store.read(ctx.baseline_ref, control)
    )
    initial = BaselineEvidenceReader(store).verify(baseline, control)
    public, private, raw_baseline = TaskBindingEvidenceReader(store).dependencies(
        initial.binding, control
    )
    selected = ClosedSourceBindingInput(
        binding=initial.binding,
        public_task=public,
        private_spec_json=private.decode() + (" " if fault == "private" else ""),
        baseline_json=raw_baseline.decode() + (" " if fault == "baseline" else ""),
    )
    if fault == "public":
        selected = selected.model_copy(
            update={
                "public_task": public.model_copy(
                    update={"goal": public.goal + " changed"}
                )
            }
        )
    before = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    if fault == "none":
        assert c.transport.read(m, c.controls.bind(c.op), binding=selected) == ctx
        assert (
            c.transport.last_reply is not None
            and c.transport.last_reply.binding == initial.binding
        )
    else:
        with pytest.raises(ClosedSourceReadFailure):
            c.transport.read(m, c.controls.bind(c.op), binding=selected)
        assert (
            c.transport.last_reply is not None
            and c.transport.last_reply.context is None
        )
        assert c.transport.last_reply.error is not None
    assert {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()} == before
    assert c.current.store.state == "ready" and not c.transport.quarantined


@pytest.mark.parametrize("fault", ["missing", "stale", "birth", "lock"])
def test_actual_namespace_and_missing_object_cannot_yield_facts(
    tmp_path: Path, installed_sources: InstalledFixture, fault: str
) -> None:
    c = actual_read_case(tmp_path, installed_sources, fresh_cas=True)
    if fault == "stale":
        other = owner_metadata_store(
            c.scope,
            c.op,
            c.clock,
            c.controls,
            c.controls.bind(c.op),
            max_io_seconds=30,
            cleanup_seconds=60,
        )
        other.store.initialize(c.controls.bind(c.op))
        other.store.put(
            b"only a fresh synthetic namespace marker",
            EvidenceMetadata(
                media_type="text/plain",
                content_schema="fault-marker/1",
                visibility="private",
                producer="fault-check",
            ),
            c.controls.bind(c.op),
        )
    elif fault == "birth":
        list((tmp_path / "sessions").glob("*.pending-*"))[0].unlink()
    elif fault == "lock":
        list((tmp_path / "sessions").glob("*.lock"))[0].unlink()
    before = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    with pytest.raises(ClosedSourceReadFailure):
        c.transport.read(c.material, c.controls.bind(c.op))
    reply = c.transport.last_reply
    assert (
        reply is not None
        and reply.error is not None
        and reply.context is None
        and reply.binding is None
    )
    if fault == "stale":
        assert reply.error.type_name == "OwnershipConflict"
    assert {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()} == before
    assert not c.transport.quarantined


class StopAfterReturn:
    def __init__(self, original: OperationControl) -> None:
        self.original, self.stopped = original, False

    def checkpoint(self) -> float:
        if self.stopped:
            raise OperationStopped("CANCELLED", "readonly-return")
        return self.original.checkpoint()

    def wait(self, seconds: float) -> None:
        self.checkpoint()
        self.original.wait(seconds)


@pytest.mark.parametrize("fault", ["cancel", "revoke", "request", "pid", "malformed"])
def test_real_child_result_rejected_after_stop_revocation_or_changed_reply(
    tmp_path: Path,
    installed_sources: InstalledFixture,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c = actual_read_case(tmp_path, installed_sources)
    original = c.transport.runner.run
    stop = StopAfterReturn(c.controls.bind(c.op))

    def run(
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        capture = original(argv, control, stdin_bytes=stdin_bytes)
        if fault == "cancel":
            stop.stopped = True
        elif fault == "revoke":
            c.current.admission.stop_new_io()
        elif fault == "malformed":
            capture = replace(capture, stdout=b"{}")
        else:
            reply = ClosedSourceReadReply.model_validate_json(capture.stdout)
            reply = (
                reply.model_copy(update={"request_sha256": "0" * 64})
                if fault == "request"
                else reply.model_copy(
                    update={
                        "worker": reply.worker.model_copy(
                            update={"process_id": reply.worker.process_id + 1}
                        )
                    }
                )
            )
            capture = replace(capture, stdout=reply.model_dump_json().encode())
        return capture

    monkeypatch.setattr(c.transport.runner, "run", run)
    with pytest.raises(
        (OperationStopped, InvalidTransition, OwnershipConflict, ValueError)
    ):
        c.transport.read(c.material, stop)
    assert c.transport.last_capture is not None
    assert c.transport.last_capture.termination is not None
    assert c.transport.last_capture.termination.state == "reaped"
    assert c.current.store.state == "ready" and not c.transport.quarantined
    with c.current.store.read_scope(c.controls.bind(c.op)):
        pass


def test_foreign_thread_and_nested_original_store_refused_before_launch(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    c = actual_read_case(tmp_path, installed_sources)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(c.transport.read, c.material, c.controls.bind(c.op))
        with pytest.raises(OwnershipConflict, match="thread"):
            future.result()
    with c.current.store.read_scope(c.controls.bind(c.op)):
        with pytest.raises(InvalidTransition, match="progress"):
            c.transport.read(c.material, c.controls.bind(c.op))
    assert c.transport.last_capture is None
