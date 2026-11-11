"""Real read-only object/temporary observations, cancellation and partial faults."""

import os
from pathlib import Path
from unittest.mock import patch
import pytest

from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.storage.evidence_worker import exchange
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.adapters.storage.inspection import inspect_exchange_storage
from lab_generate_skill.adapters.storage.inspection_result import (
    StorageInspectionFailure,
)
from lab_generate_skill.adapters.storage.temporary_identity import (
    exchange_temporary_name,
)
from lab_generate_skill.adapters.storage.worker_protocol import encode_command
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OperationStopped
from evidence_worker_fixtures import command


@pytest.mark.parametrize("data", [b"", b"evidence", b"\0\xff" * 10000])
@pytest.mark.parametrize("reading", [False, True])
def test_exact_objects_read_only_and_repeatable(
    tmp_path: Path, data: bytes, reading: bool
) -> None:
    put = command(tmp_path, data)
    exchange(encode_command(put, data))
    request = command(tmp_path, data, "read") if reading else put
    before = {
        p.name: (p.stat().st_ino, p.read_bytes())
        for p in (tmp_path / "blobs").iterdir()
    }
    with (
        patch.object(os, "mkdir", side_effect=AssertionError("create")),
        patch.object(os, "unlink", side_effect=AssertionError("delete")),
        patch.object(os, "fsync", side_effect=AssertionError("sync")),
    ):
        for _ in range(2):
            result = inspect_exchange_storage(request, DeadlineControl(5, "inspect"))
            assert result.object_state == "present"
            assert result.temporary_state == ("not_applicable" if reading else "absent")
            assert (
                result.root is not None and result.root.inode == tmp_path.stat().st_ino
            )
            assert (
                result.blobs is not None
                and result.blobs.inode == (tmp_path / "blobs").stat().st_ino
            )
    assert before == {
        p.name: (p.stat().st_ino, p.read_bytes())
        for p in (tmp_path / "blobs").iterdir()
    }


@pytest.mark.parametrize("blobs", [False, True])
def test_missing_object_is_observed_without_repair(tmp_path: Path, blobs: bool) -> None:
    if blobs:
        (tmp_path / "blobs").mkdir()
    result = inspect_exchange_storage(command(tmp_path), DeadlineControl(5, "inspect"))
    assert result.object_state == result.temporary_state == "absent"
    assert (tmp_path / "blobs").exists() is blobs


@pytest.mark.parametrize("kind", ["regular", "symlink", "fifo"])
def test_remaining_temporary_never_deleted_or_followed(
    tmp_path: Path, kind: str
) -> None:
    request = command(tmp_path)
    (tmp_path / "blobs").mkdir()
    path = tmp_path / "blobs" / exchange_temporary_name(request.exchange_id)
    outside = tmp_path / "outside"
    outside.write_bytes(b"foreign")
    if kind == "regular":
        path.write_bytes(b"unfinished")
    elif kind == "symlink":
        path.symlink_to(outside)
    else:
        os.mkfifo(path)
    original = path.lstat()
    result = inspect_exchange_storage(request, DeadlineControl(5, "inspect"))
    assert result.object_state == "absent"
    assert result.temporary_state == ("present" if kind == "regular" else "unsafe")
    assert result.temporary is not None and result.temporary.inode == original.st_ino
    assert path.lstat().st_ino == original.st_ino and outside.read_bytes() == b"foreign"


@pytest.mark.parametrize("kind", ["corrupt", "symlink", "fifo", "oversize"])
def test_invalid_object_is_unknown_not_absent(tmp_path: Path, kind: str) -> None:
    request = command(tmp_path)
    (tmp_path / "blobs").mkdir()
    path = tmp_path / "blobs" / request.reference.sha256
    if kind == "corrupt":
        path.write_bytes(b"bad")
    elif kind == "symlink":
        path.symlink_to(tmp_path / "missing")
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b"x" * (request.max_object_bytes + 1))
    inode = path.lstat().st_ino
    with pytest.raises(StorageInspectionFailure) as caught:
        inspect_exchange_storage(request, DeadlineControl(5, "inspect"))
    assert caught.value.observation.object_state == "unknown"
    assert caught.value.observation.temporary_state == "absent"
    assert path.lstat().st_ino == inode


def test_missing_and_aliased_root_are_not_initialized(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    for root in (missing, alias):
        with pytest.raises(StorageInspectionFailure):
            inspect_exchange_storage(command(root), DeadlineControl(5, "inspect"))
    assert not missing.exists() and not (tmp_path / "blobs").exists()


def test_root_replacement_invalidates_partial_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "original"
    root.mkdir()
    request = command(root)
    exchange(encode_command(request, b"evidence"))
    original = FileEvidenceStore._read_verified

    def replace_root(
        self: FileEvidenceStore, directory: int, ref: EvidenceRef
    ) -> bytes:
        data = original(self, directory, ref)
        root.rename(tmp_path / "moved")
        root.mkdir()
        (root / "blobs").mkdir()
        return data

    monkeypatch.setattr(FileEvidenceStore, "_read_verified", replace_root)
    with pytest.raises(StorageInspectionFailure) as caught:
        inspect_exchange_storage(request, DeadlineControl(5, "inspect"))
    assert caught.value.phase == "recheck"
    assert caught.value.observation.root is not None
    assert caught.value.observation.root.inode == (tmp_path / "moved").stat().st_ino


def test_expired_control_never_opens_root(tmp_path: Path) -> None:
    control = DeadlineControl(5, "expired")
    control._expires = -1
    with (
        patch.object(os, "open", side_effect=AssertionError("opened")),
        pytest.raises(OperationStopped),
    ):
        inspect_exchange_storage(command(tmp_path), control)


def test_stop_after_read_keeps_type_and_partial_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = command(tmp_path)
    exchange(encode_command(request, b"evidence"))
    control = DeadlineControl(5, "stopped")
    original = FileEvidenceStore._read_verified

    def stop(self: FileEvidenceStore, directory: int, ref: EvidenceRef) -> bytes:
        data = original(self, directory, ref)
        control._expires = -1
        return data

    monkeypatch.setattr(FileEvidenceStore, "_read_verified", stop)
    with pytest.raises(OperationStopped) as caught:
        inspect_exchange_storage(request, control)
    assert getattr(caught.value, "storage_inspection").object_state == "present"
