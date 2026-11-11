"""Declared file-scope restoration, exact input boundaries and no silent success."""

import os
from pathlib import Path
import stat
from typing import Any
import pytest
from lab_generate_skill.sites.shopping_admin.artifact_contract import (
    ARTIFACT_PATHS,
    AdminArtifactLayout,
    AdminArtifactSnapshot,
)
from lab_generate_skill.sites.shopping_admin.artifacts import AdminArtifacts
from lab_generate_skill.sites.shopping_admin.artifact_tree import tree_digest
from test_slurm_commands import guard


def layout(root: Path, **updates: Any) -> AdminArtifactLayout:
    values: dict[str, Any] = dict(
        instance_id="original",
        node_root=str(root),
        app_root=str(root / "app"),
        backup_root=str(root / "backup"),
        paths=("var/training-mail", "pub/media/training-assets"),
    )
    values.update(updates)
    return AdminArtifactLayout(**values)


def instance(root: Path) -> AdminArtifacts:
    app = root / "app"
    (app / "var/training-mail/empty").mkdir(parents=True)
    (app / "var/training-mail/message").write_bytes(b"original\0\xff")
    (app / "var/training-mail/message").chmod(0o640)
    return AdminArtifacts(layout(root))


def test_original_bytes_modes_absence_and_persisted_descriptor(tmp_path: Path) -> None:
    files = instance(tmp_path)
    saved = files.save(guard())
    assert saved.tree_sha256[0] is not None and saved.tree_sha256[1] is None
    assert stat.S_IMODE(files.backup.stat().st_mode) == 0o700
    message = files.app / "var/training-mail/message"
    message.write_bytes(b"changed")
    message.chmod(0o600)
    (message.parent / "extra").write_bytes(b"new")
    added = files.app / "pub/media/training-assets"
    added.mkdir(parents=True)
    (added / "unexpected").write_bytes(b"new")
    persisted = AdminArtifactSnapshot.model_validate_json(saved.model_dump_json())
    reloaded = AdminArtifacts(persisted.layout)
    assert reloaded.restore(persisted, guard()) == saved
    assert message.read_bytes() == b"original\0\xff"
    assert stat.S_IMODE(message.stat().st_mode) == 0o640
    assert (message.parent / "empty").is_dir()
    assert not (message.parent / "extra").exists() and not added.exists()
    assert reloaded.restore(persisted, guard()) == saved


@pytest.mark.parametrize("selected", sorted(ARTIFACT_PATHS))
def test_each_supported_scope_restores_empty_directory(
    tmp_path: Path, selected: str
) -> None:
    files = AdminArtifacts(layout(tmp_path, paths=(selected,)))
    path = files.app / selected
    path.mkdir(parents=True)
    saved = files.save(guard())
    path.rmdir()
    files.restore(saved, guard())
    assert path.is_dir() and list(path.iterdir()) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("paths", ()),
        ("paths", []),
        ("paths", None),
        ("paths", ("var/training-mail", "var/training-mail")),
        ("paths", ("../outside",)),
        ("paths", ("var",)),
        ("paths", ("/var/training-mail",)),
        ("paths", ("var/training-mail/",)),
        ("paths", (1,)),
        ("app_root", "relative"),
        ("node_root", "/"),
        ("backup_root", "/tmp/../backup"),
        ("backup_root", "/tmp//backup"),
        ("instance_id", ""),
        ("instance_id", False),
        ("app_root", None),
    ],
)
def test_invalid_contracts_have_no_effect(
    tmp_path: Path, field: str, value: Any
) -> None:
    with pytest.raises(ValueError):
        layout(tmp_path, **{field: value})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "field,relative",
    [
        ("app_root", ""),
        ("backup_root", ""),
        ("backup_root", "app"),
        ("backup_root", "app/backup"),
        ("app_root", "backup/sub"),
    ],
)
def test_overlapping_roots_refused(tmp_path: Path, field: str, relative: str) -> None:
    with pytest.raises(ValueError):
        layout(tmp_path, **{field: str(tmp_path / relative)})


def test_snapshot_wrong_scope_instance_or_length_rejected(tmp_path: Path) -> None:
    files = instance(tmp_path)
    saved = files.save(guard())
    with pytest.raises(ValueError):
        AdminArtifactSnapshot(layout=files.layout, tree_sha256=())
    other = AdminArtifactSnapshot(
        layout=layout(tmp_path, instance_id="other"), tree_sha256=saved.tree_sha256
    )
    before = tree_digest(files.app, guard())
    with pytest.raises(ValueError):
        files.restore(other, guard())
    assert tree_digest(files.app, guard()) == before


@pytest.mark.parametrize("value", [None, {}, [], True])
def test_wrong_restore_type_before_effects(tmp_path: Path, value: Any) -> None:
    files = instance(tmp_path)
    with pytest.raises(ValueError):
        files.restore(value, guard())
    assert not files.backup.exists()


def test_repeated_save_keeps_original_backup(tmp_path: Path) -> None:
    files = instance(tmp_path)
    files.save(guard())
    before = tree_digest(files.backup, guard())
    with pytest.raises(FileExistsError):
        files.save(guard())
    assert tree_digest(files.backup, guard()) == before


@pytest.mark.parametrize("corruption", ["bytes", "missing", "extra", "link", "mode"])
def test_bad_backup_rejected_before_any_target_changes(
    tmp_path: Path, corruption: str
) -> None:
    files = instance(tmp_path)
    saved = files.save(guard())
    message = files.backup / "0/message"
    if corruption == "bytes":
        message.write_bytes(b"corrupt")
    elif corruption == "missing":
        message.unlink()
    elif corruption == "extra":
        (files.backup / "unexpected").mkdir()
    elif corruption == "link":
        message.unlink()
        message.symlink_to(files.app / "var/training-mail/message")
    else:
        message.chmod(0o400)
    original = files.app / "var/training-mail/message"
    original.write_bytes(b"current state")
    with pytest.raises(ValueError):
        files.restore(saved, guard())
    assert original.read_bytes() == b"current state"


@pytest.mark.parametrize(
    "kind", ["symlink", "fifo", "hardlink", "root_file", "ancestor_link"]
)
def test_unsafe_source_rejected_before_backup(tmp_path: Path, kind: str) -> None:
    files = instance(tmp_path)
    path = files.app / "var/training-mail/message"
    outside = tmp_path / "untouched"
    outside.write_bytes(b"outside")
    if kind == "ancestor_link":
        media = files.app / "pub"
        media.symlink_to(tmp_path, target_is_directory=True)
    elif kind == "root_file":
        path.unlink()
        (path.parent / "empty").rmdir()
        path.parent.rmdir()
        path.parent.write_bytes(b"invalid root")
    else:
        path.unlink()
        if kind == "symlink":
            path.symlink_to(outside)
        elif kind == "fifo":
            os.mkfifo(path)
        else:
            os.link(outside, path)
    with pytest.raises(ValueError):
        files.save(guard())
    assert not files.backup.exists() and outside.read_bytes() == b"outside"


def test_later_unsafe_target_preflight_keeps_earlier_target(tmp_path: Path) -> None:
    files = instance(tmp_path)
    saved = files.save(guard())
    first = files.app / "var/training-mail/message"
    first.write_bytes(b"new state")
    later = files.app / "pub/media/training-assets"
    later.parent.mkdir(parents=True)
    later.symlink_to(first.parent, target_is_directory=True)
    with pytest.raises(ValueError):
        files.restore(saved, guard())
    assert first.read_bytes() == b"new state" and later.is_symlink()


def test_chunk_boundaries_and_unicode_paths(tmp_path: Path) -> None:
    files = instance(tmp_path)
    message = files.app / "var/training-mail/邮件.data"
    original = bytes(range(256)) * 8193
    message.write_bytes(original)
    saved = files.save(guard())
    message.write_bytes(b"")
    files.restore(saved, guard())
    assert message.read_bytes() == original


def test_readonly_directory_modes_restored(tmp_path: Path) -> None:
    files = instance(tmp_path)
    directory = files.app / "var/training-mail"
    directory.chmod(0o550)
    (directory / "empty").chmod(0o500)
    saved = files.save(guard())
    (directory / "message").write_bytes(b"modified")
    files.restore(saved, guard())
    assert stat.S_IMODE(directory.stat().st_mode) == 0o550
    assert stat.S_IMODE((directory / "empty").stat().st_mode) == 0o500
    assert (directory / "message").read_bytes() == b"original\0\xff"
    assert files.restore(saved, guard()) == saved


def test_symlinked_original_root_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    instance(real)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    files = AdminArtifacts(layout(link))
    with pytest.raises(ValueError):
        files.save(guard())
    assert not (real / "backup").exists()
