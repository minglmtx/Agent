"""Complete actual host persistent-file bytes, invalid roots and mid-read faults."""

import hashlib
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_runtime.persistent_state import (
    NativeMapPersistentFiles,
)
from lab_generate_skill.adapters.map_runtime import persistent_state as native
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.map_services import MapServiceSpec
from map_frontend_fixtures import frontend_case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def prepared(root: Path) -> tuple[MapServiceSpec, Path]:
    spec, files, frontend = frontend_case(root)
    frontend.prepare(guard())
    app = Path(spec.inputs.node_tree("frontend"))
    (app / "public").mkdir(mode=0o700)
    (app / "public/asset").write_bytes(b"full native asset")
    return spec, app


def test_complete_multichunk_empty_and_nested_files_use_real_host_clone(
    node_path: Path,
) -> None:
    spec, app = prepared(node_path)
    data = b"0123456789abcdef" * 150000
    (app / "storage/empty").write_bytes(b"")
    (app / "storage/nested").mkdir(mode=0o700)
    (app / "storage/nested/large").write_bytes(data)
    value = NativeMapPersistentFiles().capture(spec, guard())
    assert [p.path for p in value.files] == [
        "storage/empty",
        "storage/nested/large",
        "public/asset",
    ]
    assert (
        value.files[1].size_bytes == len(data)
        and value.files[1].sha256 == hashlib.sha256(data).hexdigest()
    )
    assert (
        value.files[0].size_bytes == 0
        and value.files[0].sha256 == hashlib.sha256(b"").hexdigest()
    )
    assert not (Path(spec.state_root("frontend")) / "app").exists()


@pytest.mark.parametrize(
    "change",
    [
        "missing-public",
        "missing-storage",
        "symlink",
        "root-alias",
        "hardlink",
        "fifo",
        "baseline",
    ],
)
def test_unknown_file_scope_never_becomes_empty_success(
    node_path: Path, change: str
) -> None:
    spec, app = prepared(node_path)
    asset = app / "public/asset"
    if change == "missing-public":
        asset.unlink()
        asset.parent.rmdir()
    elif change == "missing-storage":
        (app / "storage").rmdir()
    elif change == "symlink":
        asset.unlink()
        asset.symlink_to(app / "Gemfile.lock")
    elif change == "root-alias":
        target = app / "saved-public"
        asset.parent.rename(target)
        (app / "public").symlink_to(target, target_is_directory=True)
    elif change == "hardlink":
        os.link(asset, app / "storage/alias")
    elif change == "fifo":
        asset.unlink()
        os.mkfifo(asset)
    else:
        path = Path(spec.inputs.node_tree("app")) / "baseline.json"
        path.write_bytes(b"x" * path.stat().st_size)
    with pytest.raises((EvidenceIntegrityError, FileNotFoundError)):
        NativeMapPersistentFiles().capture(spec, guard())


@pytest.mark.parametrize("change", ["new", "modify", "remove", "new-empty-directory"])
def test_tree_change_after_file_hash_is_not_accepted(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    spec, app = prepared(node_path)
    original = native.file_pin

    def drift(root: Path, name: str, expected: tuple[int, ...], control: Any) -> Any:
        value = original(root, name, expected, control)
        if change == "new":
            (root / "storage/new").write_bytes(b"new persistent file")
        elif change == "modify":
            (root / name).write_bytes(b"same-size-drift!!")
        elif change == "remove":
            (root / name).unlink()
        else:
            (root / "storage/new-dir").mkdir(mode=0o700)
        return value

    monkeypatch.setattr(native, "file_pin", drift)
    with pytest.raises(EvidenceIntegrityError, match="tree changed"):
        NativeMapPersistentFiles().capture(spec, guard())


def test_read_and_close_failures_preserved_together(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, app = prepared(node_path)
    read, close = os.read, os.close
    primary, cleanup = OSError("original file read failed"), OSError(
        "original file close failed"
    )
    target_fd: int | None = None

    def fail_read(fd: int, size: int) -> bytes:
        nonlocal target_fd
        if os.readlink(f"/proc/self/fd/{fd}") == str(app / "public/asset"):
            target_fd = fd
            raise primary
        return read(fd, size)

    def fail_close(fd: int) -> None:
        close(fd)
        if fd == target_fd:
            raise cleanup

    with monkeypatch.context() as patch:
        patch.setattr(os, "read", fail_read)
        patch.setattr(os, "close", fail_close)
        with pytest.raises(BaseExceptionGroup) as caught:
            NativeMapPersistentFiles().capture(spec, guard())
    assert caught.value.exceptions == (primary, cleanup)


def test_cancellation_mid_full_file_hash_preserves_original_file(
    node_path: Path,
) -> None:
    spec, app = prepared(node_path)
    before = native.scan(app, guard())
    name = "public/asset"
    calls = 0

    class Stop:
        def checkpoint(self) -> float:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise TimeoutError("cancelled before full file read")
            return 60.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError):
        native.file_pin(app, name, before[name], Stop())
    assert (app / name).read_bytes() == b"full native asset"
