"""Real partial files and combined write/close errors remain observable."""

import os
import stat
from pathlib import Path

import pytest

from lab_generate_skill.domain.errors import EvidenceIntegrityError
from artifact_freeze_fixtures import fixture
from test_atomic_snapshot import flatten
from test_slurm_commands import guard


def test_write_and_both_close_errors_retain_primary_and_partial_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    freezer, source = fixture(tmp_path)
    opened: set[int] = set()
    real_open, real_close = os.open, os.close

    def open_file(
        path: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        fd = real_open(path, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]
        if str(path).endswith("data.bin"):
            opened.add(fd)
        return fd

    def close_file(fd: int) -> None:
        real_close(fd)
        if fd in opened:
            opened.remove(fd)
            raise OSError("close data fd")

    def write_file(fd: int, data: object) -> int:
        raise OSError("original write failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", open_file)
        patch.setattr(os, "close", close_file)
        patch.setattr(os, "write", write_file)
        with pytest.raises(ExceptionGroup) as error:
            freezer.freeze(source, "v1", guard())
    messages = [str(item) for item in flatten(error.value)]
    assert messages == ["original write failure", "close data fd", "close data fd"]
    assert not opened and getattr(error.value, "artifact_freeze").destination_created
    candidate = tmp_path / "published/v1"
    assert (candidate / "nested/data.bin").read_bytes() == b""
    with pytest.raises(EvidenceIntegrityError):
        freezer.freeze(source, "v1", guard())


@pytest.mark.parametrize(
    "boundary", ["file_sync", "first_directory_sync", "final_directory_sync"]
)
def test_sync_failure_keeps_original_candidate_and_no_false_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    freezer, source = fixture(tmp_path)
    target = tmp_path / "published/v1"
    original = os.fsync

    def sync(fd: int) -> None:
        is_file = stat.S_ISREG(os.fstat(fd).st_mode)
        should_fail = (
            (boundary == "file_sync" and is_file)
            or (boundary == "first_directory_sync" and not is_file)
            or (
                boundary == "final_directory_sync"
                and not is_file
                and target.exists()
                and not target.stat().st_mode & 0o222
            )
        )
        if should_fail:
            raise OSError(boundary)
        original(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", sync)
        with pytest.raises(OSError, match=boundary) as error:
            freezer.freeze(source, "v1", guard())
    assert (
        getattr(error.value, "artifact_freeze").destination_created and target.exists()
    )
    if boundary == "final_directory_sync":
        assert freezer.freeze(source, "v1", guard()).root == str(target)


def test_complete_unconfirmed_target_requires_durability_on_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    freezer, source = fixture(tmp_path)
    target = tmp_path / "published/v1"
    real_sync = os.fsync

    def fail_final_sync(fd: int) -> None:
        if target.exists() and not target.stat().st_mode & 0o222:
            raise OSError("original directory sync failure")
        real_sync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail_final_sync)
        with pytest.raises(OSError, match="original directory sync failure"):
            freezer.freeze(source, "v1", guard())
    assert target.exists() and not target.stat().st_mode & 0o222

    def fail_replay_sync(fd: int) -> None:
        raise OSError("replay durability failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail_replay_sync)
        with pytest.raises(OSError, match="replay durability failure") as error:
            freezer.freeze(source, "v1", guard())
    assert not getattr(error.value, "artifact_freeze").destination_created
    assert freezer.freeze(source, "v1", guard()).root == str(target)
