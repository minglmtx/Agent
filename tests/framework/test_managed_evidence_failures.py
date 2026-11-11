"""Original stop/error and independent resolution across the real installed chain."""

from pathlib import Path
from dataclasses import replace
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
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
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.ports.lifecycle import OperationControl
from managed_store_fixtures import assembled
from test_filesystem_evidence import metadata
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_unconfirmed_original_exit_keeps_public_instance_isolated(
    tmp_path: Path, installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, _ = assembled(tmp_path, installed_sources)
    store.initialize(guard(60))
    original_run = ProcessRunner.run
    calls: list[tuple[str, ...]] = []

    def run(
        self: ProcessRunner,
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        capture = original_run(self, argv, control, stdin_bytes=stdin_bytes)
        calls.append(argv)
        if argv[-1] == "lab_generate_skill.bootstrap.evidence_worker":
            assert capture.termination is not None
            return replace(
                capture,
                termination=ProcessTermination(
                    capture.termination.process_id, "unconfirmed", None, True
                ),
            )
        return capture

    monkeypatch.setattr(ProcessRunner, "run", run)
    with pytest.raises(RegisteredStorageFailure):
        store.put(b"actual committed bytes", metadata(), guard(60))
    assert store.state == "quarantined" and store.last_exchange is not None
    result = store.last_exchange
    assert (
        result.failed_execution is not None and result.failed_execution.ending is None
    )
    assert result.resolution is not None and result.snapshot is not None
    assert result.snapshot.revision == 3 and not result.reusable
    resolution = result.snapshot.entries[-1].resolutions[-1]
    assert (
        resolution.worker_end is None
        and resolution.object_state == resolution.cleanup_state == "unknown"
    )
    assert len(calls) == 2
    with pytest.raises(InvalidTransition):
        store.put(b"actual committed bytes", metadata(), guard(60))
    assert len(calls) == 2
    # A fresh Python object cannot turn the same durable quarantine into an
    # empty session. Restore observation before testing actual initialization.
    monkeypatch.setattr(ProcessRunner, "run", original_run)
    path = next((tmp_path / "sessions").glob("*.evidence-session.json"))
    before = path.read_bytes()
    another, _ = assembled(tmp_path, installed_sources, provision=False)
    with pytest.raises(InvalidTransition, match="not ready"):
        another.initialize(guard(60))
    assert another.state == "quarantined" and path.read_bytes() == before


def test_original_cancel_after_reply_still_records_independent_cleanup(
    tmp_path: Path, installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, admission = assembled(tmp_path, installed_sources)
    store.initialize(guard(60))

    class Caller:
        stopped = False

        def checkpoint(self) -> float:
            if self.stopped:
                raise OperationStopped("CANCELLED", "original-business")
            return 60

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    caller = Caller()
    original_run = ProcessRunner.run
    calls: list[tuple[str, ...]] = []

    def run(
        self: ProcessRunner,
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        result = original_run(self, argv, control, stdin_bytes=stdin_bytes)
        calls.append(argv)
        if argv[-1] == "lab_generate_skill.bootstrap.evidence_worker":
            caller.stopped = True
        return result

    monkeypatch.setattr(ProcessRunner, "run", run)
    with pytest.raises(RegisteredStorageFailure) as failed:
        store.put(b"committed", metadata(), caller)
    assert isinstance(failed.value.__cause__, OperationStopped)
    assert store.state == "ready" and store.last_exchange is not None
    result = store.last_exchange
    assert (
        result.primary is failed.value
        and result.reusable
        and result.cleanup_error is None
    )
    assert (
        result.failed_execution is not None
        and result.failed_execution.ending is not None
    )
    assert result.resolution is not None and result.snapshot is not None
    assert result.snapshot.revision == 3
    assert (
        admission.calls[-1].mode == "cleanup"
        and admission.calls[-1].cancellation_ref is None
    )
    assert [a[-1] for a in calls] == [
        "lab_generate_skill.bootstrap.evidence_worker",
        "lab_generate_skill.bootstrap.evidence_resolver",
    ]


def test_primary_and_resolution_ack_loss_remain_separate_without_retry(
    tmp_path: Path, installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, admission = assembled(tmp_path, installed_sources)
    store.initialize(guard(60))
    original_resolve = StorageResolverTransport.execute
    lost = OSError("original resolution committed; acknowledgement lost")
    committed: list[StorageResolutionExecution] = []

    def resolve(
        self: StorageResolverTransport,
        cmd: StorageResolutionCommand,
        payload: bytes,
        control: OperationControl,
    ) -> StorageResolutionExecution:
        committed.append(original_resolve(self, cmd, payload, control))
        raise lost

    monkeypatch.setattr(StorageResolverTransport, "execute", resolve)
    ref = evidence_reference(b"missing", metadata())
    with pytest.raises(BaseExceptionGroup) as failed:
        store.read(ref, guard(60))
    assert len(failed.value.exceptions) == 2 and failed.value.exceptions[1] is lost
    assert isinstance(failed.value.exceptions[0], RegisteredStorageFailure)
    assert len(committed) == 1 and committed[0].result.snapshot is not None
    assert committed[0].result.snapshot.entries[-1].reusable
    assert store.state == "quarantined" and store.last_exchange is not None
    assert store.last_exchange.cleanup_error is lost
    before = len(admission.calls)
    with pytest.raises(InvalidTransition):
        store.read(ref, guard(60))
    assert len(admission.calls) == before


def test_execute_admission_denial_has_no_spawn_or_history_change(
    tmp_path: Path, installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, admission = assembled(tmp_path, installed_sources)
    store.initialize(guard(60))
    path = next((tmp_path / "sessions").glob("*.evidence-session.json"))
    before = path.read_bytes()
    admission.denied = True

    def unexpected(*args: object, **kwargs: object) -> CommandCapture:
        raise AssertionError("denial must precede launch")

    monkeypatch.setattr(ProcessRunner, "run", unexpected)
    with pytest.raises(PermissionError):
        store.put(b"data", metadata(), guard(60))
    assert store.state == "ready" and store.last_exchange is not None
    assert not store.last_exchange.attempted and store.last_exchange.resolution is None
    assert path.read_bytes() == before and not (tmp_path / "data" / "blobs").exists()
