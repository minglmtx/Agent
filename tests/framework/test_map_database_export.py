"""Exclusive native output leaf: full bytes, hostile files and partial failures."""

import hashlib
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime import database_export as leaf
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.map_database_export import MapDatabaseExport
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.sites.map.native_database_program import reference_program
from map_instance_fixtures import InstanceCase
from map_database_capture_fixtures import BOUNDS
from test_map_instance import case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


@pytest.fixture
def export(
    case: InstanceCase,
) -> tuple[leaf.NativeMapDatabaseExportFiles, MapDatabaseExport, bytes]:
    case.instance.prepare(guard(60))
    program = reference_program(BOUNDS, "request0", 16 * 1024**2)
    plan = MapDatabaseExport(
        spec=case.spec,
        label="request0",
        max_output_bytes=16 * 1024**2,
        program=ReleaseFile(
            path="reference.rb",
            sha256=hashlib.sha256(program).hexdigest(),
            size_bytes=len(program),
            executable=False,
        ),
    )
    return leaf.NativeMapDatabaseExportFiles(), plan, program


def output(plan: MapDatabaseExport, data: bytes) -> Path:
    path = Path(plan.host_directory) / plan.output_name
    path.write_bytes(data)
    path.chmod(0o400)
    return path


@pytest.mark.parametrize("size", [0, 1, 1024**2 + 7, 16 * 1024**2])
def test_complete_bytes_boundary_and_duplicate_preparation(
    export: tuple[leaf.NativeMapDatabaseExportFiles, MapDatabaseExport, bytes],
    size: int,
) -> None:
    files, plan, program = export
    files.prepare(plan, program, guard())
    data = b"x" * size
    path = output(plan, data)
    assert files.read(plan, guard()) == data
    with pytest.raises(FileExistsError):
        files.prepare(plan, program, guard())
    assert path.read_bytes() == data


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "extra",
        "mutable",
        "symlink",
        "hardlink",
        "fifo",
        "directory",
        "oversize",
        "program",
        "intent",
    ],
)
def test_invalid_native_output_retained_rejected(
    export: tuple[leaf.NativeMapDatabaseExportFiles, MapDatabaseExport, bytes],
    kind: str,
) -> None:
    files, plan, program = export
    files.prepare(plan, program, guard())
    root = Path(plan.host_directory)
    path = output(plan, b"actual bytes")
    if kind == "missing":
        path.unlink()
    elif kind == "extra":
        (root / "unexpected").write_bytes(b"extra")
    elif kind == "mutable":
        path.chmod(0o600)
    elif kind == "symlink":
        path.unlink()
        path.symlink_to(root / "reference.rb")
    elif kind == "hardlink":
        os.link(path, root.parent / "held-output")
    elif kind == "fifo":
        path.unlink()
        os.mkfifo(path, 0o400)
    elif kind == "directory":
        path.unlink()
        path.mkdir(mode=0o400)
    elif kind == "oversize":
        path.chmod(0o600)
        with path.open("wb") as stream:
            stream.truncate(plan.max_output_bytes + 1)
        path.chmod(0o400)
    else:
        target = root / ("reference.rb" if kind == "program" else "intent.json")
        target.chmod(0o600)
        target.write_bytes(b"corrupted")
    with pytest.raises((EvidenceIntegrityError, FileNotFoundError)):
        files.read(plan, guard())
    assert root.exists()
    if kind == "directory":
        path.chmod(0o700)


def test_wrong_program_rejected_before_reservation(
    export: tuple[leaf.NativeMapDatabaseExportFiles, MapDatabaseExport, bytes],
) -> None:
    files, plan, program = export
    with pytest.raises(EvidenceIntegrityError):
        files.prepare(plan, program + b"x", guard())
    assert not Path(plan.host_directory).exists()


def test_partial_prepare_keeps_reservation_and_never_overwrites(
    export: tuple[leaf.NativeMapDatabaseExportFiles, MapDatabaseExport, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files, plan, program = export
    error = OSError("original parent fsync failed")

    def failed(path: Path) -> None:
        raise error

    monkeypatch.setattr(leaf, "sync_directory", failed)
    with pytest.raises(OSError) as caught:
        files.prepare(plan, program, guard())
    assert caught.value is error and Path(plan.host_directory).is_dir()
    with pytest.raises(FileExistsError):
        files.prepare(plan, program, guard())


def test_read_race_detected_without_cleanup(
    export: tuple[leaf.NativeMapDatabaseExportFiles, MapDatabaseExport, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files, plan, program = export
    files.prepare(plan, program, guard())
    path = output(plan, b"native bytes")
    original = os.read
    changed = False

    def read(fd: int, count: int) -> bytes:
        nonlocal changed
        data = original(fd, count)
        if not changed and os.fstat(fd).st_ino == path.stat().st_ino:
            changed = True
            path.chmod(0o600)
            path.write_bytes(b"changed bytes")
            path.chmod(0o400)
        return data

    monkeypatch.setattr(os, "read", read)
    with pytest.raises(EvidenceIntegrityError):
        files.read(plan, guard())
    assert changed and path.read_bytes() == b"changed bytes"


@pytest.mark.parametrize(
    "changes",
    [
        {"label": "../x"},
        {"label": ""},
        {"label": 3},
        {"max_output_bytes": True},
        {"max_output_bytes": 0},
        {"max_output_bytes": 2 * 1024**4 + 1},
        {"program": None},
    ],
)
def test_export_boundary_contract(
    export: tuple[leaf.NativeMapDatabaseExportFiles, MapDatabaseExport, bytes],
    changes: dict[str, Any],
) -> None:
    _, plan, _ = export
    with pytest.raises(ValueError):
        MapDatabaseExport.model_validate({**plan.model_dump(), **changes})
