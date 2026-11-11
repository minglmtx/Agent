"""Exact tree identities, controlled copying and deletion of selected directories."""

import hashlib
import json
import os
from pathlib import Path
import stat
from lab_generate_skill.ports.lifecycle import OperationControl
from .artifact_io import CHUNK_BYTES, checked_path, copy_file, held_file, identity


def _file_hash(path: Path, control: OperationControl) -> str:
    digest = hashlib.sha256()
    with held_file(path, os.O_RDONLY) as fd:
        before = os.fstat(fd)
        while True:
            control.checkpoint()
            block = os.read(fd, CHUNK_BYTES)
            if not block:
                break
            digest.update(block)
        if identity(before) != identity(os.fstat(fd)) or identity(before) != identity(
            path.lstat()
        ):
            raise ValueError("Artifact changed during hashing")
    return digest.hexdigest()


def _entries(root: Path, control: OperationControl) -> list[Path]:
    result = [root]

    def visit(directory: Path) -> None:
        control.checkpoint()
        for child in sorted(directory.iterdir()):
            control.checkpoint()
            mode = child.lstat().st_mode
            if stat.S_ISDIR(mode):
                result.append(child)
                visit(child)
            elif stat.S_ISREG(mode) and child.lstat().st_nlink == 1:
                result.append(child)
            else:
                raise ValueError("Unsupported artifact entry")

    visit(root)
    return result


def tree_digest(root: Path, control: OperationControl) -> str | None:
    checked_path(root, control)
    try:
        info = root.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Artifact root must be a directory or absent")
    rows: list[tuple[object, ...]] = []
    for path in _entries(root, control):
        control.checkpoint()
        info = path.lstat()
        name, mode = path.relative_to(root).as_posix(), stat.S_IMODE(info.st_mode)
        if stat.S_ISDIR(info.st_mode):
            rows.append((name, "directory", mode))
        else:
            digest = _file_hash(path, control)
            if identity(info) != identity(path.lstat()):
                raise ValueError("Artifact changed while recording metadata")
            rows.append((name, "file", mode, info.st_size, digest))
    control.checkpoint()
    return hashlib.sha256(
        json.dumps(sorted(rows), ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def copy_tree(source: Path, target: Path, control: OperationControl) -> None:
    checked_path(source, control)
    checked_path(target, control)
    entries = _entries(source, control)
    # Create writable directories, then restore their original modes last.
    target.mkdir(mode=0o700)
    directories: list[tuple[Path, int]] = []
    for entry in entries:
        control.checkpoint()
        destination = target / entry.relative_to(source)
        mode = entry.lstat().st_mode
        if stat.S_ISDIR(mode):
            if entry != source:
                destination.mkdir(mode=0o700)
            directories.append((destination, stat.S_IMODE(mode)))
        else:
            copy_file(entry, destination, control)
    for directory, mode in reversed(directories):
        control.checkpoint()
        directory.chmod(mode)


def remove_tree(root: Path, control: OperationControl) -> None:
    # Validate all entries before the first deletion. Caller owns quiescence.
    if tree_digest(root, control) is None:
        return
    entries = _entries(root, control)
    # Only the already-validated private deletion targets are made writable.
    # Backup modes are untouched and copy_tree restores original target modes.
    for entry in entries:
        control.checkpoint()
        mode = entry.lstat().st_mode
        if stat.S_ISDIR(mode):
            entry.chmod(stat.S_IMODE(mode) | stat.S_IWUSR | stat.S_IXUSR)
    for entry in reversed(entries):
        control.checkpoint()
        if stat.S_ISDIR(entry.lstat().st_mode):
            entry.rmdir()
        else:
            entry.unlink()
