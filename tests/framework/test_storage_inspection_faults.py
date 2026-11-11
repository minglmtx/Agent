"""Combination faults retain the first failure and every owned-fd close error."""

import os
from pathlib import Path
from unittest.mock import patch
import pytest
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.adapters.storage.inspection import inspect_exchange_storage
from lab_generate_skill.adapters.storage.inspection_result import (
    StorageInspectionFailure,
)
from lab_generate_skill.adapters.storage.temporary_identity import (
    exchange_temporary_name,
)
from evidence_worker_fixtures import command


def test_object_and_temporary_errors_both_retained(tmp_path: Path) -> None:
    request = command(tmp_path)
    (tmp_path / "blobs").mkdir()
    object_error, temporary_error = OSError("object"), PermissionError("temporary")
    original_stat = os.stat

    def statted(
        path: str | Path, *, dir_fd: int | None = None, follow_symlinks: bool = True
    ) -> os.stat_result:
        if path == exchange_temporary_name(request.exchange_id):
            raise temporary_error
        return original_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    with (
        patch.object(FileEvidenceStore, "_read_verified", side_effect=object_error),
        patch.object(os, "stat", side_effect=statted),
        pytest.raises(StorageInspectionFailure) as caught,
    ):
        inspect_exchange_storage(request, DeadlineControl(5, "inspect"))
    assert caught.value.phase == "checks"
    cause = caught.value.__cause__
    assert isinstance(cause, ExceptionGroup)
    assert cause.exceptions == (object_error, temporary_error)
    assert (
        caught.value.observation.object_state
        == caught.value.observation.temporary_state
        == "unknown"
    )


@pytest.mark.parametrize("object_failure", [False, True])
def test_both_directory_closes_attempted_and_original_failure_preserved(
    tmp_path: Path, object_failure: bool
) -> None:
    request = command(tmp_path)
    (tmp_path / "blobs").mkdir()
    original_open, original_close = os.open, os.close
    owned: list[int] = []
    closed: list[int] = []
    first = OSError("original read")

    def opened(
        path: str | Path, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        fd = original_open(path, flags, mode, dir_fd=dir_fd)
        if len(owned) < 2:
            owned.append(fd)
        return fd

    def close(fd: int) -> None:
        original_close(fd)
        if fd in owned:
            closed.append(fd)
            raise OSError("owned close")

    def read(self: FileEvidenceStore, directory: int, reference: object) -> bytes:
        if object_failure:
            raise first
        return b"evidence"

    with (
        patch.object(os, "open", side_effect=opened),
        patch.object(os, "close", side_effect=close),
        patch.object(FileEvidenceStore, "_read_verified", read),
        pytest.raises(StorageInspectionFailure) as caught,
    ):
        inspect_exchange_storage(request, DeadlineControl(5, "inspect"))
    cause = caught.value.__cause__
    assert isinstance(cause, ExceptionGroup)
    assert closed == list(reversed(owned)) and len(closed) == 2
    if object_failure:
        primary = cause.exceptions[0]
        assert isinstance(primary, ExceptionGroup) and primary.exceptions == (first,)
        assert len(cause.exceptions) == 3
    else:
        assert caught.value.phase == "close" and len(cause.exceptions) == 2
