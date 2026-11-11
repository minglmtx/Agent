"""Bounded pinned metadata read failure/cancellation and original close errors."""

import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime.metadata import read_pinned_bytes
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from map_runtime_fixtures import save
from test_site_files import Stop
from test_slurm_commands import guard


@pytest.mark.parametrize("change", ["digest", "size", "executable", "alias", "fifo"])
def test_bad_metadata_preserved_and_refused(tmp_path: Path, change: str) -> None:
    path = tmp_path / "receipt.json"
    pin = save(path, {"passed": True})
    if change == "digest":
        path.write_bytes(b"x" * pin.size_bytes)
    elif change == "size":
        path.write_bytes(b"x")
    elif change == "executable":
        path.chmod(0o700)
    elif change == "alias":
        real = tmp_path / "real.json"
        path.rename(real)
        path.symlink_to(real)
    else:
        path.unlink()
        os.mkfifo(path)
    with pytest.raises(EvidenceIntegrityError):
        read_pinned_bytes(path, pin, guard())
    assert path.exists()


@pytest.mark.parametrize("at", [1, 2, 3, 4])
def test_cancel_preserves_metadata(tmp_path: Path, at: int) -> None:
    path = tmp_path / "receipt.json"
    pin = save(path, {"passed": True})
    original = path.read_bytes()
    with pytest.raises(TimeoutError):
        read_pinned_bytes(path, pin, Stop(at))
    assert path.read_bytes() == original
    assert read_pinned_bytes(path, pin, guard()) == original


def test_read_and_close_errors_both_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "receipt.json"
    pin = save(path, {"passed": True})
    close = os.close
    primary, cleanup = OSError("metadata read failed"), OSError("metadata close failed")

    def fail_read(*args: Any) -> bytes:
        raise primary

    def fail_close(fd: int) -> None:
        close(fd)
        raise cleanup

    with monkeypatch.context() as patch:
        patch.setattr(os, "read", fail_read)
        patch.setattr(os, "close", fail_close)
        with pytest.raises(BaseExceptionGroup) as caught:
            read_pinned_bytes(path, pin, guard())
    assert caught.value.exceptions == (primary, cleanup)


def test_path_replacement_during_read_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "receipt.json"
    pin = save(path, {"passed": True})
    read = os.read
    moved = False

    def replace(fd: int, size: int) -> bytes:
        nonlocal moved
        body = read(fd, size)
        if not moved:
            moved = True
            path.rename(tmp_path / "original.json")
            path.write_bytes(b"replacement")
        return body

    monkeypatch.setattr(os, "read", replace)
    with pytest.raises(EvidenceIntegrityError):
        read_pinned_bytes(path, pin, guard())
