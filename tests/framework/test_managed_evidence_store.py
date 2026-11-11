"""Public port to actual isolated installed workers; no file primitive fallback."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import EvidenceError, InvalidTransition
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageFailure,
)
from managed_store_fixtures import assembled
from test_filesystem_evidence import metadata
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_new_instance_explicitly_reads_closed_history_without_reset(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    original, _ = assembled(tmp_path, installed_sources)
    original.initialize(guard(60))
    ref = original.put(b"original", metadata(), guard(60))
    prior = original.last_exchange
    assert prior is not None and prior.snapshot is not None
    path = next((tmp_path / "sessions").glob("*.evidence-session.json"))
    before = path.read_bytes()
    another, _ = assembled(tmp_path, installed_sources, provision=False)
    assert another.initialize(guard(60)) == prior.snapshot
    assert path.read_bytes() == before
    assert another.read(ref, guard(60)) == b"original"
    current = another.last_exchange
    assert current is not None and current.snapshot is not None
    assert current.snapshot.revision == 6
    assert current.snapshot.entries[0] == prior.snapshot.entries[0]


@pytest.mark.parametrize("data", [b"", b"\x00\xff\n", b"a" * 1024])
def test_installed_public_port_roundtrip_and_repeated_bytes(
    tmp_path: Path, installed_sources: InstalledFixture, data: bytes
) -> None:
    managed, admission = assembled(tmp_path, installed_sources)
    store: EvidenceStore = managed
    initial_state = managed.state
    assert initial_state == "new"
    assert managed.initialize(guard(60)).revision == 0
    ref = store.put(data, metadata(), guard(60))
    assert store.put(data, metadata(), guard(60)) == ref
    assert store.read(ref, guard(60)) == data
    assert managed.state == "ready"
    result = managed.last_exchange
    assert result is not None and result.reusable and result.snapshot is not None
    assert result.snapshot.revision == 9 and len(result.snapshot.entries) == 3
    assert len({e.intent.exchange_id for e in result.snapshot.entries}) == 3
    assert len(admission.calls) == 7  # explicit create; execute/cleanup for each I/O
    assert len(list((tmp_path / "data" / "blobs").iterdir())) == 1
    with pytest.raises(InvalidTransition):
        managed.initialize(guard(60))
    assert len(admission.calls) == 7


def test_missing_read_remains_failed_but_clean_store_accepts_next_io(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    store, _ = assembled(tmp_path, installed_sources)
    store.initialize(guard(60))
    ref = evidence_reference(b"missing", metadata())
    with pytest.raises(RegisteredStorageFailure):
        store.read(ref, guard(60))
    assert store.state == "ready" and store.last_exchange is not None
    assert store.last_exchange.reusable and store.last_exchange.primary is not None
    assert store.put(b"missing", metadata(), guard(60)) == ref
    assert store.read(ref, guard(60)) == b"missing"


def test_missing_used_history_never_reinitializes_or_retries(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    store, admission = assembled(tmp_path, installed_sources)
    store.initialize(guard(60))
    path = next((tmp_path / "sessions").glob("*.evidence-session.json"))
    path.unlink()
    with pytest.raises(BaseExceptionGroup) as failed:
        store.put(b"data", metadata(), guard(60))
    assert len(failed.value.exceptions) == 2
    assert store.state == "quarantined" and not path.exists()
    before = len(admission.calls)
    with pytest.raises(InvalidTransition):
        store.put(b"data", metadata(), guard(60))
    with pytest.raises(InvalidTransition):
        store.initialize(guard(60))
    assert len(admission.calls) == before and not (tmp_path / "data" / "blobs").exists()


def test_corrupt_object_preserves_original_bytes_and_isolates(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    store, _ = assembled(tmp_path, installed_sources)
    store.initialize(guard(60))
    ref = store.put(b"original", metadata(), guard(60))
    path = tmp_path / "data" / "blobs" / ref.sha256
    path.write_bytes(b"corrupt")
    with pytest.raises(BaseExceptionGroup) as failed:
        store.read(ref, guard(60))
    assert isinstance(failed.value.exceptions[0], EvidenceError)
    assert store.state == "quarantined" and path.read_bytes() == b"corrupt"
    assert (
        store.last_exchange is not None
        and store.last_exchange.cleanup_error is not None
    )
