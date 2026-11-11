"""Failure boundaries: validate before effects, preserve errors and published bytes."""

import hashlib
import os
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata


def metadata() -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/octet-stream",
        content_schema="capture/1",
        visibility="private",
        producer="fault-test",
    )


@pytest.mark.parametrize("invalid", [None, {}, "metadata", 0, False])
def test_bad_metadata_has_no_disk_effect(tmp_path: Path, invalid: object) -> None:
    store = FileEvidenceStore(tmp_path)
    with pytest.raises((TypeError, ValidationError)):
        store.put(b"valid payload", cast(EvidenceMetadata, invalid))
    assert list((tmp_path / "blobs").iterdir()) == []


@pytest.mark.parametrize("invalid", [None, "text", 1, False, [], bytearray(b"x")])
def test_only_immutable_bytes_accepted(tmp_path: Path, invalid: object) -> None:
    store = FileEvidenceStore(tmp_path)
    with pytest.raises(TypeError):
        store.put(cast(bytes, invalid), metadata())
    assert list((tmp_path / "blobs").iterdir()) == []


def test_bypassed_metadata_validation_rechecked_before_write(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    invalid = metadata().model_copy(update={"visibility": "unclassified"})
    with pytest.raises(ValidationError):
        store.put(b"payload", invalid)
    assert list((tmp_path / "blobs").iterdir()) == []


def test_primary_and_all_cleanup_errors_remain_distinct(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    original_close = os.close
    primary = OSError("link failed")
    unlink_error = OSError("unlink failed")
    closed: list[int] = []

    def close_then_fail(fd: int) -> None:
        original_close(fd)
        closed.append(fd)
        raise OSError("close failed")

    with (
        patch.object(os, "link", side_effect=primary),
        patch.object(os, "unlink", side_effect=unlink_error),
        patch.object(os, "close", side_effect=close_then_fail),
        pytest.raises(BaseExceptionGroup) as caught,
    ):
        store.put(b"payload", metadata())
    assert caught.value.exceptions[0] is primary
    assert unlink_error in caught.value.exceptions[1:]
    assert len(closed) >= 1
    assert sum(str(e) == "close failed" for e in caught.value.exceptions) == len(closed)
    files = list((tmp_path / "blobs").iterdir())
    assert len(files) == 1 and files[0].name.startswith(".pending-")
    assert files[0].read_bytes() == b"payload"


@pytest.mark.parametrize("boundary", ["write", "file_fsync", "link"])
def test_prepublication_failure_leaves_no_blob(tmp_path: Path, boundary: str) -> None:
    store = FileEvidenceStore(tmp_path)
    error = OSError(boundary)
    target = {"write": "write", "file_fsync": "fsync", "link": "link"}[boundary]
    with patch.object(os, target, side_effect=error), pytest.raises(OSError) as caught:
        store.put(b"payload", metadata())
    assert caught.value is error
    assert list((tmp_path / "blobs").iterdir()) == []


@pytest.mark.parametrize("boundary", ["directory_fsync", "unlink", "close"])
def test_postpublication_failure_can_reconcile_same_bytes(
    tmp_path: Path, boundary: str
) -> None:
    store = FileEvidenceStore(tmp_path)
    data = b"committed payload"
    digest = hashlib.sha256(data).hexdigest()
    if boundary == "directory_fsync":
        failure = patch.object(os, "fsync", side_effect=[None, OSError("lost ack")])
    elif boundary == "unlink":
        failure = patch.object(os, "unlink", side_effect=OSError("cleanup"))
    else:
        original_close = os.close

        def close_then_fail(fd: int) -> None:
            original_close(fd)
            raise OSError("cleanup")

        failure = patch.object(os, "close", side_effect=close_then_fail)
    with failure, pytest.raises((OSError, ExceptionGroup)):
        store.put(data, metadata())
    path = tmp_path / "blobs" / digest
    assert path.read_bytes() == data
    inode = path.stat().st_ino
    ref = store.put(data, metadata())
    assert ref.sha256 == digest and store.read(ref) == data
    assert path.stat().st_ino == inode
    assert len(list((tmp_path / "blobs").glob(".pending-*"))) == (
        1 if boundary == "unlink" else 0
    )


def test_exclusive_create_collision_does_not_remove_foreign_pending(
    tmp_path: Path,
) -> None:
    store = FileEvidenceStore(tmp_path)
    from uuid import UUID

    identity = UUID(int=42)
    path = tmp_path / "blobs" / (".pending-" + identity.hex)
    path.write_bytes(b"other writer")
    with (
        patch(
            "lab_generate_skill.adapters.storage.filesystem.uuid.uuid4",
            return_value=identity,
        ),
        pytest.raises(FileExistsError),
    ):
        store.put(b"payload", metadata())
    assert path.read_bytes() == b"other writer"


def test_short_writes_publish_complete_bytes(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    original_write = os.write
    calls: list[int] = []

    def short_write(fd: int, data: bytes) -> int:
        calls.append(len(data))
        return original_write(fd, data[:2])

    with patch.object(os, "write", side_effect=short_write):
        ref = store.put(b"seven!!", metadata())
    assert calls == [7, 5, 3, 1]
    assert store.read(ref) == b"seven!!"


def test_zero_write_stops_without_publishing(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    with patch.object(os, "write", return_value=0), pytest.raises(OSError):
        store.put(b"payload", metadata())
    assert list((tmp_path / "blobs").iterdir()) == []
