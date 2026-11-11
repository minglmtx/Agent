"""Uncertain atomic commits keep original pointer facts and all close errors."""

import os
from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.atomic_snapshot import (
    AtomicSnapshotFile,
    SnapshotTransaction,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from release_current_fixtures import store, op, switch, disk
from test_slurm_commands import guard


@pytest.mark.parametrize("fault", ["write", "replace", "sync"])
def test_failed_switch_retains_old_or_complete_new_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    ledger = store(tmp_path)
    ledger.initialize(op())
    first = switch()
    ledger.activate(first)
    old = (tmp_path / "system-current.json").read_bytes()
    change = switch(1, "two")
    actual = getattr(os, "fsync" if fault == "sync" else fault)
    calls = 0

    def fail(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if fault != "sync" or calls == 2:
            raise OSError("injected current " + fault)
        return actual(*args, **kwargs)

    name = "fsync" if fault == "sync" else fault
    monkeypatch.setattr(os, name, fail)
    with pytest.raises(OSError, match="injected current") as caught:
        ledger.activate(change)
    candidate = getattr(caught.value, "release_current_candidate")
    assert candidate.active == change.activation
    data = (tmp_path / "system-current.json").read_bytes()
    assert data == (candidate.model_dump_json().encode() if fault == "sync" else old)
    assert not any(p.name.startswith(".pending-snapshot-") for p in tmp_path.iterdir())
    monkeypatch.setattr(os, name, actual)
    confirmed = ledger.activate(change)
    assert confirmed == candidate and ledger.read(op("read")) == candidate


def test_replay_requires_successful_sync_not_just_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = store(tmp_path)
    ledger.initialize(op())
    change = switch()
    ledger.activate(change)
    before = disk(tmp_path)

    def fail(fd: int) -> None:
        raise OSError("confirm not durable")

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail)
        with pytest.raises(OSError, match="confirm not durable") as caught:
            ledger.activate(change)
    assert getattr(caught.value, "release_current_candidate").revision == 1
    assert disk(tmp_path) == before
    assert ledger.activate(change).revision == 1


def test_post_commit_two_close_errors_keep_candidate_and_release_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = store(tmp_path)
    ledger.initialize(op())
    change = switch()
    actual_write = SnapshotTransaction.write
    actual_close = os.close
    committed = False
    closed: list[int] = []

    def write(transaction: SnapshotTransaction, raw: bytes) -> None:
        nonlocal committed
        actual_write(transaction, raw)
        committed = True

    def close(fd: int) -> None:
        actual_close(fd)
        if committed:
            closed.append(fd)
            raise OSError("close after commit")

    with monkeypatch.context() as patch:
        patch.setattr(SnapshotTransaction, "write", write)
        patch.setattr(os, "close", close)
        with pytest.raises(ExceptionGroup) as caught:
            ledger.activate(change)
    assert len(caught.value.exceptions) == 2 and len(closed) == 2
    for fd in closed:
        with pytest.raises(OSError):
            os.fstat(fd)
    candidate = getattr(caught.value, "release_current_candidate")
    assert (
        candidate.active == change.activation and ledger.read(op("read")) == candidate
    )


def test_initialization_sync_failure_never_recreates_empty_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = store(tmp_path)

    def fail(fd: int) -> None:
        raise OSError("birth sync unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail)
        with pytest.raises(OSError) as caught:
            ledger.initialize(op())
    assert getattr(caught.value, "release_current_candidate").revision == 0
    before = disk(tmp_path)
    with pytest.raises(EvidenceIntegrityError):
        ledger.initialize(op("new-init"))
    assert disk(tmp_path) == before


@pytest.mark.parametrize("name", ["system-current.json", "a" * 64 + ".unit.json"])
def test_snapshot_confirm_preserves_inode_and_bytes(tmp_path: Path, name: str) -> None:
    storage = AtomicSnapshotFile(tmp_path, name, max_bytes=100)
    with storage.locked(guard()) as transaction:
        with pytest.raises(EvidenceIntegrityError):
            transaction.confirm()
        transaction.write(b"original")
        inode = (tmp_path / name).stat().st_ino
        transaction.confirm()
        assert transaction.read() == b"original"
        assert (tmp_path / name).stat().st_ino == inode


@pytest.mark.parametrize(
    "name",
    [
        "../system-current.json",
        "current.json",
        "system-current.json/extra",
        "/system-current.json",
        "",
    ],
)
def test_atomic_name_extension_is_exact(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        AtomicSnapshotFile(tmp_path, name, max_bytes=100)
    assert disk(tmp_path) == {}
