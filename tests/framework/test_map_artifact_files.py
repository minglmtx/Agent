"""Complete file publication and readback; no production Map authority or services."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.map_private_artifact import (
    MapPrivateArtifactPlan,
    MapArtifactHandle,
)
from lab_generate_skill.domain.errors import InvalidTransition, EvidenceIntegrityError
from map_artifact_fixtures import case
from test_slurm_commands import guard


def test_complete_files_private_handle_and_independent_readback(tmp_path: Path) -> None:
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    entries = [
        writer.retain("native-error.txt", b"original HTTP400", guard()),
        writer.retain("empty-partial.bin", b"", guard()),
    ]
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    manifest = reader.manifest(handle, guard())
    assert (
        list(manifest.artifact.files) == entries
        and len(handle.model_dump_json()) < 1024
    )
    assert reader.read(handle, "native-error.txt", guard()) == b"original HTTP400"
    assert reader.read(handle, "empty-partial.bin", guard()) == b""
    assert not (writer.root.stat().st_mode & 0o077) and not (
        writer.published.stat().st_mode & 0o222
    )
    with pytest.raises(InvalidTransition):
        writer.retain("later", b"x", guard())
    with pytest.raises(InvalidTransition):
        writer.seal(guard())
    assert writer.handle == handle and writer.state == "sealed"


def test_actual_above_cas_limit_file_never_truncated(tmp_path: Path) -> None:
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    payload = b"0123456789abcdef" * (4 * 1024 * 1024) + b"full-tail"
    entry = writer.retain("complete-union.osm", payload, guard())
    handle = writer.seal(guard(60))
    restored = MapArtifactReader(writer.plan, tmp_path, authority).read(
        handle, entry.path, guard(60)
    )
    assert (
        len(restored) > 64 * 1024 * 1024
        and restored == payload
        and hashlib.sha256(restored).hexdigest() == entry.sha256
    )


@pytest.mark.parametrize("phase", ["initialize", "write", "seal", "read"])
def test_original_authority_denial_precedes_effect(tmp_path: Path, phase: str) -> None:
    w, a = case(tmp_path)
    if phase != "initialize":
        w.initialize(guard())
    if phase in ("seal", "read"):
        w.retain("one", b"bytes", guard())
    handle = w.seal(guard()) if phase == "read" else None
    a.denied = True
    with pytest.raises(PermissionError):
        if phase == "initialize":
            w.initialize(guard())
        elif phase == "write":
            w.retain("one", b"x", guard())
        elif phase == "seal":
            w.seal(guard())
        else:
            assert handle is not None
            MapArtifactReader(w.plan, tmp_path, a).read(handle, "one", guard())
    if phase == "initialize":
        assert not w.root.exists()
    if phase == "write":
        assert not list(w.working.iterdir())
    if phase == "seal":
        assert not list(w.published.iterdir())


@pytest.mark.parametrize(
    "name,data",
    [
        ("", b""),
        ("../escape", b"a"),
        ("/abs", b"a"),
        ("nested/file", b"a"),
        ("a\x00b", b""),
        ("a" * 129, b""),
        ("x", None),
        ("x", "bytes"),
        (42, b""),
    ],
)
def test_invalid_file_inputs_have_no_effect(
    tmp_path: Path, name: Any, data: Any
) -> None:
    w, a = case(tmp_path)
    w.initialize(guard())
    calls = list(a.calls)
    with pytest.raises(ValueError):
        w.retain(name, data, guard())
    assert not list(w.working.iterdir()) and a.calls == calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_files", 0),
        ("max_files", True),
        ("max_files", 10001),
        ("max_file_bytes", -1),
        ("max_total_bytes", 1),
        ("private_root", "/tmp/not-workspace"),
        ("producer", "other"),
    ],
)
def test_invalid_plan_rejected(tmp_path: Path, field: str, value: object) -> None:
    w, _ = case(tmp_path)
    data = w.plan.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        MapPrivateArtifactPlan.model_validate(data)
    assert not w.root.exists()


def test_duplicate_budget_and_unlisted_data_are_rejected(tmp_path: Path) -> None:
    w, a = case(tmp_path, file_budget=3, total_budget=4, max_files=2)
    w.initialize(guard())
    w.retain("a", b"123", guard())
    with pytest.raises(InvalidTransition):
        w.retain("a", b"old overwritten", guard())
    with pytest.raises(ValueError):
        w.retain("b", b"12", guard())
    with pytest.raises(ValueError):
        w.retain("too-large", b"12345", guard())
    w.retain("b", b"4", guard())
    with pytest.raises(ValueError):
        w.retain("c", b"", guard())
    handle = w.seal(guard())
    with pytest.raises(EvidenceIntegrityError):
        MapArtifactReader(w.plan, tmp_path, a).read(handle, "../a", guard())


@pytest.mark.parametrize("fault", ["existing", "symlink", "public-parent"])
def test_unsafe_root_never_reused_or_widened(tmp_path: Path, fault: str) -> None:
    w, _ = case(tmp_path)
    if fault == "existing":
        w.root.mkdir()
        (w.root / "keep").write_bytes(b"original")
    elif fault == "symlink":
        w.root.symlink_to(tmp_path, target_is_directory=True)
    else:
        tmp_path.chmod(0o755)
    with pytest.raises((OSError, EvidenceIntegrityError)):
        w.initialize(guard())
    if fault == "existing":
        assert (w.root / "keep").read_bytes() == b"original"
    if fault == "symlink":
        assert w.root.is_symlink()
    if fault == "public-parent":
        assert not w.root.exists()


def test_concurrent_writes_serialize_and_seal_stops_new_writers(tmp_path: Path) -> None:
    w, a = case(tmp_path)
    w.initialize(guard())
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(w.retain, str(i), str(i).encode(), guard()) for i in range(10)
        ]
        assert len([f.result() for f in futures]) == 10
    handle = w.seal(guard())
    manifest = MapArtifactReader(w.plan, tmp_path, a).manifest(handle, guard())
    assert len(manifest.artifact.files) == 10


@pytest.mark.parametrize("fault", ["bytes", "extra", "symlink", "writable", "manifest"])
def test_readback_refuses_changed_artifact(tmp_path: Path, fault: str) -> None:
    w, a = case(tmp_path)
    w.initialize(guard())
    w.retain("one", b"known", guard())
    handle = w.seal(guard())
    root = w.published / "sealed"
    path = root / "one"
    if fault == "bytes":
        path.chmod(0o600)
        path.write_bytes(b"other")
        path.chmod(0o444)
    elif fault == "extra":
        root.chmod(0o700)
        (root / "extra").write_bytes(b"extra")
        (root / "extra").chmod(0o444)
        root.chmod(0o555)
    elif fault == "symlink":
        root.chmod(0o700)
        path.unlink()
        path.symlink_to(w.working / "one")
        root.chmod(0o555)
    elif fault == "writable":
        path.chmod(0o600)
    else:
        path = w.published / "manifest.json"
        path.chmod(0o600)
        path.write_bytes(b"{}")
        path.chmod(0o444)
    with pytest.raises(EvidenceIntegrityError):
        MapArtifactReader(w.plan, tmp_path, a).manifest(handle, guard())


def test_partial_write_kept_and_never_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    w, _ = case(tmp_path)
    w.initialize(guard())
    original = os.write
    calls = 0

    def fail(fd: int, data: Any) -> int:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected disk failure")
        return original(fd, data[:2])

    monkeypatch.setattr(os, "write", fail)
    with pytest.raises(OSError, match="disk failure"):
        w.retain("partial", b"full-body", guard())
    assert (w.working / "partial").read_bytes() == b"fu" and w.state == "failed"
    with pytest.raises(InvalidTransition):
        w.retain("partial", b"full-body", guard())
    with pytest.raises(InvalidTransition):
        w.seal(guard())


def test_cancellation_after_first_chunk_preserves_partial_and_prevents_seal(
    tmp_path: Path,
) -> None:
    w, _ = case(tmp_path)
    w.initialize(guard())

    class Stopped:
        def checkpoint(self) -> float:
            p = w.working / "partial"
            if p.exists() and p.stat().st_size:
                raise TimeoutError("cancelled after partial bytes")
            return 30.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError):
        w.retain("partial", b"x" * (2 * 1024 * 1024), Stopped())
    assert (w.working / "partial").stat().st_size == 1024 * 1024 and w.state == "failed"
    with pytest.raises(InvalidTransition):
        w.seal(guard())


def test_wrong_plan_handle_rejected_before_reader_authority(tmp_path: Path) -> None:
    w, a = case(tmp_path)
    w.initialize(guard())
    w.retain("a", b"a", guard())
    h = w.seal(guard())
    calls = list(a.calls)
    data = h.model_dump()
    data["plan_sha256"] = "a" * 64
    other = MapArtifactHandle.model_validate(data)
    with pytest.raises(EvidenceIntegrityError):
        MapArtifactReader(w.plan, tmp_path, a).manifest(other, guard())
    assert a.calls == calls
