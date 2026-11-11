"""Actual fixed installed child rejects an expired request before durable intent.

The preparation double supplies an already-expired transmitted deadline while
keeping the original parent supervision live: a deterministic late-launch race,
not timing sleeps or a different child program. No original I/O is reissued.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evidence_operations import (
    EvidenceOperationFactory,
    PreparedStorageOperation,
)
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageFailure,
)
from lab_generate_skill.adapters.storage.resolver_transport import (
    StorageResolverTransport,
    StorageResolutionExecution,
)
from lab_generate_skill.adapters.storage.resolver_protocol import (
    StorageResolutionCommand,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    ProcessTermination,
    CommandCapture,
)
from lab_generate_skill.domain.evidence_identity import evidence_reference
from managed_store_fixtures import assembled
from test_filesystem_evidence import metadata
from test_slurm_commands import guard
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker


@dataclass(frozen=True)
class LatePreparation:
    operation: OperationContext
    control: OperationControl


class ExpiredChildOperation:
    def __init__(self, original: EvidenceOperationFactory) -> None:
        self.original = original
        self.binding = original.binding

    def prepare(
        self, exchange_id: str, control: OperationControl
    ) -> PreparedStorageOperation:
        prepared = self.original.prepare(exchange_id, control)
        return LatePreparation(
            prepared.operation.model_copy(
                update={
                    "deadline": datetime.now(timezone.utc) - timedelta(seconds=1),
                }
            ),
            prepared.control,
        )


@pytest.mark.parametrize("used", [False, True])
def test_confirmed_unregistered_child_preserves_failure_and_allows_different_cleanup(
    tmp_path: Path,
    installed_sources: InstalledFixture,
    monkeypatch: pytest.MonkeyPatch,
    used: bool,
) -> None:
    store, _ = assembled(tmp_path, installed_sources)
    store.initialize(guard(60))
    if used:
        store.put(b"prior accepted history", metadata(), guard(60))
    history = next((tmp_path / "sessions").glob("*.evidence-session.json"))
    before = history.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(store, "_operations", ExpiredChildOperation(store._operations))
        with pytest.raises(RegisteredStorageFailure):
            store.put(b"never issued physical IO", metadata(), guard(60))
    failed = store.last_exchange
    assert failed is not None and failed.reusable and failed.primary is not None
    assert (
        failed.failed_execution is not None
        and failed.failed_execution.ending is not None
    )
    assert (
        failed.resolution is not None
        and failed.resolution.result.reply.not_registered is not None
    )
    assert failed.resolution.result.reply.schema_version == "storage-resolution-reply/4"
    assert history.read_bytes() == before and store.state == "ready"
    missing = evidence_reference(b"never issued physical IO", metadata())
    assert not (tmp_path / "data/blobs" / missing.sha256).exists()
    # Different cleanup diagnostics, never an automatic repeat of failed payload.
    ref = store.put(b"new cleanup diagnostics", metadata(), guard(60))
    assert store.read(ref, guard(60)) == b"new cleanup diagnostics"
    assert (
        store.last_exchange is not None and store.last_exchange.command.io is not None
    )
    assert failed.command.io is not None
    assert store.last_exchange.command.io.exchange_id != failed.command.io.exchange_id


@pytest.mark.parametrize(
    "fault", ["unknown_end", "used_history_missing", "used_history_changed"]
)
def test_absence_without_end_or_original_history_stays_quarantined(
    tmp_path: Path,
    installed_sources: InstalledFixture,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    store, _ = assembled(tmp_path, installed_sources)
    store.initialize(guard(60))
    store.put(b"used", metadata(), guard(60))
    history = next((tmp_path / "sessions").glob("*.evidence-session.json"))
    old_run = ProcessRunner.run
    old_resolve = StorageResolverTransport.execute

    def run(
        self: ProcessRunner,
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        capture = old_run(self, argv, control, stdin_bytes=stdin_bytes)
        if (
            argv[-1] == "lab_generate_skill.bootstrap.evidence_worker"
            and fault == "unknown_end"
        ):
            assert capture.termination is not None
            return replace(
                capture,
                termination=ProcessTermination(
                    capture.termination.process_id, "unconfirmed", None, True
                ),
            )
        return capture

    def resolve(
        self: StorageResolverTransport,
        command: StorageResolutionCommand,
        payload: bytes,
        control: OperationControl,
    ) -> StorageResolutionExecution:
        if fault == "used_history_missing":
            history.unlink()
        elif fault == "used_history_changed":
            before = EvidenceSessionSnapshot.model_validate_json(history.read_bytes())
            first = before.entries[0]
            assert first.outcome is not None
            changed = EvidenceSessionSnapshot.model_validate(
                before.model_copy(
                    update={
                        "entries": (
                            first.model_copy(
                                update={
                                    "outcome": first.outcome.model_copy(
                                        update={"reply_sha256": "f" * 64}
                                    ),
                                }
                            ),
                            *before.entries[1:],
                        ),
                    }
                )
            )
            assert changed.revision == before.revision and changed != before
            history.write_bytes(changed.model_dump_json().encode())
        return old_resolve(self, command, payload, control)

    monkeypatch.setattr(ProcessRunner, "run", run)
    monkeypatch.setattr(StorageResolverTransport, "execute", resolve)
    monkeypatch.setattr(store, "_operations", ExpiredChildOperation(store._operations))
    with pytest.raises(BaseExceptionGroup):
        store.put(b"must remain unissued", metadata(), guard(60))
    assert store.state == "quarantined" and store.last_exchange is not None
    assert (
        not store.last_exchange.reusable
        and store.last_exchange.cleanup_error is not None
    )
    if fault == "used_history_missing":
        assert not history.exists()
    elif fault == "used_history_changed":
        # Independent resolver observed no original intent, but the original
        # controller rejects changed prior history despite identical revision.
        assert store.last_exchange.resolution is not None
        assert store.last_exchange.resolution.result.reply.not_registered is not None
