"""Fault effects are retained; failed restore never advertises a clean instance."""

import os
from pathlib import Path
import pytest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin import artifact_io, artifacts
from lab_generate_skill.sites.shopping_admin.artifact_tree import (
    tree_digest,
    remove_tree,
)
from test_admin_artifacts import instance
from test_slurm_commands import guard


class Stop:
    def __init__(self) -> None:
        self.error = RuntimeError("original cancellation")

    def checkpoint(self) -> float:
        raise self.error

    def wait(self, seconds: float) -> None:
        raise AssertionError("unused")


def test_cancel_before_save_or_restore_has_no_effect(tmp_path: Path) -> None:
    files = instance(tmp_path)
    stopped = Stop()
    with pytest.raises(RuntimeError) as error:
        files.save(stopped)
    assert error.value is stopped.error and not files.backup.exists()
    saved = files.save(guard())
    before = tree_digest(files.app, guard())
    with pytest.raises(RuntimeError) as error:
        files.restore(saved, stopped)
    assert error.value is stopped.error and tree_digest(files.app, guard()) == before


def test_failed_save_leaves_partial_snapshot_and_does_not_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = instance(tmp_path)
    first = OSError("disk full")

    def fail(source: Path, target: Path, control: OperationControl) -> None:
        target.mkdir()
        (target / "partial").write_bytes(b"partial")
        raise first

    monkeypatch.setattr(artifacts, "copy_tree", fail)
    with pytest.raises(OSError) as caught:
        files.save(guard())
    assert (
        caught.value is first
        and (files.backup / "0/partial").read_bytes() == b"partial"
    )
    with pytest.raises(FileExistsError):
        files.save(guard())
    assert (files.app / "var/training-mail/message").read_bytes() == b"original\0\xff"


def test_partial_restore_preserves_error_and_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = instance(tmp_path)
    saved = files.save(guard())
    baseline = tree_digest(files.backup, guard())
    first = OSError("restore write failed")

    def fail(source: Path, target: Path, control: OperationControl) -> None:
        target.mkdir()
        raise first

    monkeypatch.setattr(artifacts, "copy_tree", fail)
    with pytest.raises(OSError) as caught:
        files.restore(saved, guard())
    assert caught.value is first
    assert tree_digest(files.backup, guard()) == baseline
    assert list((files.app / "var/training-mail").iterdir()) == []


def test_write_and_close_failure_preserve_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"copy")
    primary, cleanup = OSError("write"), OSError("close")
    real_close = os.close

    def write(fd: int, data: object) -> int:
        raise primary

    calls = 0

    def close(fd: int) -> None:
        nonlocal calls
        calls += 1
        real_close(fd)
        if calls == 1:
            raise cleanup

    monkeypatch.setattr(os, "write", write)
    monkeypatch.setattr(os, "close", close)
    with pytest.raises(BaseExceptionGroup) as caught:
        artifact_io.copy_file(source, target, guard())
    assert caught.value.exceptions == (primary, cleanup)
    assert calls == 2 and target.read_bytes() == b"" and source.read_bytes() == b"copy"


def test_short_writes_are_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"0123456789")
    real_write = os.write

    def write(fd: int, data: memoryview) -> int:
        return real_write(fd, data[:2])

    monkeypatch.setattr(os, "write", write)
    artifact_io.copy_file(source, target, guard())
    assert target.read_bytes() == source.read_bytes()


def test_cancel_during_copy_retains_partial_bytes_and_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"x" * (artifact_io.CHUNK_BYTES + 10))
    real_write = os.write
    error = RuntimeError("cancel during copy")
    stopped = False

    class Control:
        def checkpoint(self) -> float:
            if stopped:
                raise error
            return 5.0

        def wait(self, seconds: float) -> None:
            raise AssertionError("unused")

    def write(fd: int, data: memoryview) -> int:
        nonlocal stopped
        count = real_write(fd, data)
        stopped = True
        return count

    monkeypatch.setattr(os, "write", write)
    with pytest.raises(RuntimeError) as caught:
        artifact_io.copy_file(source, target, Control())
    assert caught.value is error
    assert target.read_bytes() == b"x" * artifact_io.CHUNK_BYTES
    assert source.stat().st_size == artifact_io.CHUNK_BYTES + 10


def test_zero_write_fails_without_spinning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"original")

    def write(fd: int, data: memoryview) -> int:
        return 0

    monkeypatch.setattr(os, "write", write)
    with pytest.raises(OSError, match="no progress"):
        artifact_io.copy_file(source, target, guard())
    assert target.read_bytes() == b"" and source.read_bytes() == b"original"


def test_source_change_during_hash_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "file"
    source.write_bytes(b"original")
    real_read = os.read
    mutated = False

    def read(fd: int, size: int) -> bytes:
        nonlocal mutated
        data = real_read(fd, size)
        if not mutated:
            source.write_bytes(b"changed and longer")
            mutated = True
        return data

    monkeypatch.setattr(os, "read", read)
    with pytest.raises(ValueError, match="changed"):
        tree_digest(tmp_path, guard())


def test_stop_after_removal_preserves_original_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = instance(tmp_path)
    saved = files.save(guard())
    original = tree_digest(files.backup, guard())
    real_remove = remove_tree
    error = RuntimeError("stop after removal")

    def remove(root: Path, control: OperationControl) -> None:
        real_remove(root, control)
        raise error

    monkeypatch.setattr(artifacts, "remove_tree", remove)
    with pytest.raises(RuntimeError) as caught:
        files.restore(saved, guard())
    assert caught.value is error
    assert not (files.app / "var/training-mail").exists()
    assert tree_digest(files.backup, guard()) == original
