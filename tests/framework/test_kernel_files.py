"""Actual descriptor IO, links, bounds, cancellation and combined close faults."""

import os
from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.adapters.slurm import kernel_files as module
from cgroup_fixtures import Control


@pytest.mark.parametrize("length", [0, 7, 8, 9])
def test_read_boundary_and_repeat(tmp_path: Path, length: int) -> None:
    path = tmp_path / "record"
    path.write_bytes(b"x" * length)
    if length > 8:
        with pytest.raises(ValueError) as caught:
            module.read_kernel_file(path, 8, Control())
        assert getattr(caught.value, "kernel_read_capture").content == b"x" * 9
    else:
        for _ in range(2):
            result = module.read_kernel_file(path, 8, Control())
            assert result.content == b"x" * length and result.complete
    assert path.read_bytes() == b"x" * length


@pytest.mark.parametrize(
    "kind", ["file_link", "directory_link", "fifo", "directory", "missing"]
)
def test_no_links_or_special_records(tmp_path: Path, kind: str) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "record").write_bytes(b"data")
    target = tmp_path / "target"
    if kind == "file_link":
        target.symlink_to(real / "record")
    elif kind == "directory_link":
        target.symlink_to(real, target_is_directory=True)
        target = target / "record"
    elif kind == "fifo":
        os.mkfifo(target)
    elif kind == "directory":
        target.mkdir()
    with pytest.raises((OSError, ValueError)):
        module.read_kernel_file(target, 10, Control())


@pytest.mark.parametrize("limit", [0, -1, 1024 * 1024 + 1, True, "10", None])
def test_bad_limit_before_open(
    tmp_path: Path, limit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> int:
        raise AssertionError("bad argument opened a file")

    monkeypatch.setattr(os, "open", forbidden)
    with pytest.raises(ValueError):
        module.read_kernel_file(tmp_path / "x", limit, Control())


def test_read_and_close_failure_preserve_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "record"
    path.write_bytes(b"data")
    real_close = os.close
    closed: list[int] = []

    def fail_read(fd: int, size: int) -> bytes:
        raise OSError("original read fault")

    def fail_close(fd: int) -> None:
        real_close(fd)
        closed.append(fd)
        raise OSError("independent close fault")

    with monkeypatch.context() as m:
        m.setattr(os, "read", fail_read)
        m.setattr(os, "close", fail_close)
        with pytest.raises(ExceptionGroup) as caught:
            module.read_kernel_file(path, 10, Control())
    assert str(caught.value.exceptions[0]) == "original read fault"
    assert len(caught.value.exceptions) == len(closed) + 1
    assert len(closed) >= 2 and len(set(closed)) == len(closed)
    assert getattr(caught.value, "kernel_read_capture").complete is False


def test_cancel_preserves_type_and_releases_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "record"
    path.write_bytes(b"data")
    real_open, real_close = os.open, os.close
    opened: list[int] = []
    closed: list[int] = []

    class Stop(Control):
        count = 0

        def checkpoint(self) -> float:
            self.count += 1
            if self.count == 3:
                raise TimeoutError("deadline")
            return 10

    def open_record(*args: Any, **kwargs: Any) -> int:
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def close_record(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    with monkeypatch.context() as m:
        m.setattr(os, "open", open_record)
        m.setattr(os, "close", close_record)
        with pytest.raises(TimeoutError, match="deadline"):
            module.read_kernel_file(path, 10, Stop())
    assert opened and closed == list(reversed(opened))


def test_read_detects_path_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, replacement = tmp_path / "record", tmp_path / "replacement"
    path.write_bytes(b"original")
    replacement.write_bytes(b"different")
    real_read = os.read
    replaced = False

    def read(fd: int, size: int) -> bytes:
        nonlocal replaced
        data = real_read(fd, size)
        if not replaced:
            os.replace(replacement, path)
            replaced = True
        return data

    monkeypatch.setattr(os, "read", read)
    with pytest.raises(ValueError, match="identity changed") as caught:
        module.read_kernel_file(path, 100, Control())
    assert getattr(caught.value, "kernel_read_capture").content == b"original"


@pytest.mark.parametrize(
    "uid,gid,mode,writable",
    [
        (1000, 0, 0o100644, False),
        (0, 1000, 0o100644, False),
        (0, 0, 0o100664, False),
        (0, 0, 0o100646, False),
        (0, 0, 0o100644, True),
    ],
)
def test_control_rejects_delegated_or_writable_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    uid: int,
    gid: int,
    mode: int,
    writable: bool,
) -> None:
    path = tmp_path / "control"
    path.write_bytes(b"")
    real_fstat = os.fstat

    def fake_fstat(fd: int) -> os.stat_result:
        values = list(real_fstat(fd))
        values[0], values[4], values[5] = mode, uid, gid
        return os.stat_result(values)

    monkeypatch.setattr(os, "fstat", fake_fstat)
    monkeypatch.setattr(os, "access", lambda *a, **kw: writable)
    with pytest.raises(ValueError, match="root managed") as caught:
        module.inspect_control(path, Control(), directory=False)
    record = getattr(caught.value, "kernel_control_capture")
    assert (record.uid, record.gid, record.mode, record.writable) == (
        uid,
        gid,
        mode,
        writable,
    )
