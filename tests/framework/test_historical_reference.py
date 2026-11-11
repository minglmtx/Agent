"""Exact mapped reading with no access to original paths, execution or mutation."""

import hashlib
import os
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.bootstrap.historical_reading import open_historical_reader
from lab_generate_skill.adapters.storage.historical_reference import (
    WorkspaceHistoricalReader,
)
from lab_generate_skill.adapters.storage import historical_files
from lab_generate_skill.domain.historical_reference import (
    HistoricalKey,
    HistoricalFile,
    HistoricalReferenceMap,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OperationStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from test_slurm_commands import guard


def fixture(
    root: Path, raw: bytes = b"original"
) -> tuple[HistoricalReferenceMap, HistoricalKey, Path]:
    sha = hashlib.sha256(raw).hexdigest()
    key = HistoricalKey(original_path="/unmounted/old/evidence.json", sha256=sha)
    relative = "records/" + sha + "/evidence.json"
    target = root / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    return (
        HistoricalReferenceMap(
            files=(
                HistoricalFile(key=key, relative_path=relative, size_bytes=len(raw)),
            )
        ),
        key,
        target,
    )


@pytest.mark.parametrize("raw", [b"", b"original", "原始数据".encode(), b"x" * 1048577])
def test_actual_bytes_without_original_path_and_repeat(
    tmp_path: Path, raw: bytes
) -> None:
    mapping, key, target = fixture(tmp_path, raw)
    reader = WorkspaceHistoricalReader(tmp_path, mapping)
    assert reader.read(key, guard()) == raw
    assert reader.read(key, guard()) == raw
    assert target.read_bytes() == raw
    manifest = tmp_path / "read-map.json"
    manifest.write_bytes(mapping.model_dump_json().encode())
    loaded = open_historical_reader(
        tmp_path,
        manifest.name,
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
        guard(),
    )
    assert loaded.read(key, guard()) == raw


@pytest.mark.parametrize(
    "change",
    [
        {"original_path": "relative"},
        {"original_path": "/old/../new"},
        {"sha256": ""},
        {"sha256": True},
        {"extra": 1},
    ],
)
def test_invalid_key_rejects(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HistoricalKey.model_validate(
            {"original_path": "/old/file", "sha256": "a" * 64, **change}
        )


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "escape",
        "wrong_digest_path",
        "wrong_size_type",
        "negative_size",
        "over_size",
    ],
)
def test_invalid_mapping_rejects(tmp_path: Path, fault: str) -> None:
    mapping, key, target = fixture(tmp_path)
    entry = mapping.files[0]
    if fault == "duplicate":
        broken = mapping.model_copy(update={"files": (entry, entry)})
    else:
        updates: dict[str, dict[str, object]] = {
            "escape": {"relative_path": "records/../else"},
            "wrong_digest_path": {"relative_path": "records/" + "b" * 64 + "/file"},
            "wrong_size_type": {"size_bytes": True},
            "negative_size": {"size_bytes": -1},
            "over_size": {"size_bytes": 512 * 1024 * 1024 + 1},
        }
        update = updates[fault]
        broken = mapping.model_copy(
            update={"files": (entry.model_copy(update=update),)}
        )
    with pytest.raises(ValidationError):
        WorkspaceHistoricalReader(tmp_path, broken)


@pytest.mark.parametrize(
    "fault",
    [
        "unmapped",
        "wrong_hash",
        "missing",
        "corrupt",
        "size",
        "leaf_link",
        "directory_link",
        "root_link",
    ],
)
def test_bad_reference_fails_without_old_path_fallback(
    tmp_path: Path, fault: str
) -> None:
    mapping, key, target = fixture(tmp_path)
    root = tmp_path
    if fault == "unmapped":
        key = key.model_copy(update={"original_path": "/other"})
    elif fault == "wrong_hash":
        key = key.model_copy(update={"sha256": "b" * 64})
    elif fault == "missing":
        target.unlink()
    elif fault == "corrupt":
        target.write_bytes(b"corrupt!")
    elif fault == "size":
        target.write_bytes(b"changed size")
    elif fault == "leaf_link":
        copy = tmp_path / "copy"
        copy.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(copy)
    elif fault == "directory_link":
        parent = target.parent
        moved = tmp_path / "moved"
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
    else:
        root = tmp_path / "alias"
        root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises((EvidenceIntegrityError, EvidenceNotFound, OSError)):
        WorkspaceHistoricalReader(root, mapping).read(key, guard())


def test_two_versions_of_same_original_path_require_exact_digest(
    tmp_path: Path,
) -> None:
    first, key, _ = fixture(tmp_path)
    second, other, _ = fixture(tmp_path, b"second version")
    reader = WorkspaceHistoricalReader(
        tmp_path, HistoricalReferenceMap(files=(*first.files, *second.files))
    )
    assert reader.read(key, guard()) == b"original"
    assert reader.read(other, guard()) == b"second version"


def test_map_hash_duplicate_json_and_oversize_refused(tmp_path: Path) -> None:
    mapping, _, _ = fixture(tmp_path)
    manifest = tmp_path / "read-map.json"
    manifest.write_bytes(mapping.model_dump_json().encode())
    with pytest.raises(EvidenceIntegrityError):
        open_historical_reader(tmp_path, manifest.name, "0" * 64, guard())
    manifest.write_bytes(b'{"files":[],"files":[]}')
    with pytest.raises(ValueError):
        open_historical_reader(
            tmp_path,
            manifest.name,
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            guard(),
        )
    with manifest.open("wb") as stream:
        stream.truncate(16 * 1024 * 1024 + 1)
    with pytest.raises(EvidenceIntegrityError):
        open_historical_reader(tmp_path, manifest.name, "0" * 64, guard())


@pytest.mark.parametrize(
    "fault", ["mutation", "cancel_during_read", "directory_missing", "fifo"]
)
def test_read_boundaries_preserve_failure_and_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    mapping, key, target = fixture(
        tmp_path, b"x" * (2 * 1024 * 1024) if fault == "mutation" else b"original"
    )
    real_read = os.read
    real_close = os.close
    closed: list[int] = []

    def closing(fd: int) -> None:
        real_close(fd)
        closed.append(fd)

    def interrupted(fd: int, count: int) -> bytes:
        raw = real_read(fd, count)
        if fault == "mutation":
            if raw and len(raw) == 1024 * 1024:
                with target.open("r+b") as writer:
                    writer.seek(1024 * 1024)
                    writer.write(b"modified")
                    writer.flush()
                    os.fsync(writer.fileno())
        else:
            raise OperationStopped("CANCELLED", "during_read")
        return raw

    if fault in ("mutation", "cancel_during_read"):
        monkeypatch.setattr(os, "read", interrupted)
    elif fault == "directory_missing":
        target.unlink()
        target.parent.rmdir()
    else:
        target.unlink()
        os.mkfifo(target)
    monkeypatch.setattr(os, "close", closing)
    with pytest.raises((EvidenceIntegrityError, EvidenceNotFound, OperationStopped)):
        WorkspaceHistoricalReader(tmp_path, mapping).read(key, guard())
    assert closed


def test_cli_returns_exact_bytes_and_rejects_wrong_pin(tmp_path: Path) -> None:
    import subprocess
    import sys

    mapping, key, _ = fixture(tmp_path)
    manifest = tmp_path / "read-map.json"
    manifest.write_bytes(mapping.model_dump_json().encode())
    tool = Path(__file__).resolve().parents[2] / "tools/read_historical_reference.py"
    args = [
        sys.executable,
        "-B",
        str(tool),
        "--root",
        str(tmp_path),
        "--map",
        manifest.name,
        "--map-sha256",
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "--original-path",
        key.original_path,
        "--sha256",
        key.sha256,
    ]
    completed = subprocess.run(args, capture_output=True, timeout=15, check=True)
    assert completed.stdout == b"original" and not completed.stderr
    args[-1] = "0" * 64
    rejected = subprocess.run(args, capture_output=True, timeout=15, check=False)
    assert rejected.returncode != 0 and not rejected.stdout
    assert b"Exact historical version is not mapped" in rejected.stderr


def test_cancel_and_primary_plus_close_failure_survive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapping, key, _ = fixture(tmp_path)
    reader = WorkspaceHistoricalReader(tmp_path, mapping)
    control = guard()
    failure = OperationStopped("CANCELLED", "read")

    def stopped() -> float:
        raise failure

    monkeypatch.setattr(control, "checkpoint", stopped)
    with pytest.raises(OperationStopped) as caught:
        reader.read(key, control)
    assert caught.value is failure
    real_close = os.close
    main = OSError("read failed")
    cleanup = OSError("close failed")

    def bad_read(fd: int, count: int) -> bytes:
        raise main

    def bad_close(fd: int) -> None:
        real_close(fd)
        raise cleanup

    monkeypatch.setattr(os, "read", bad_read)
    monkeypatch.setattr(os, "close", bad_close)
    with pytest.raises(BaseExceptionGroup) as grouped:
        reader.read(key, guard())
    assert grouped.value.exceptions[0] is main
    assert all(e is cleanup for e in grouped.value.exceptions[1:])
