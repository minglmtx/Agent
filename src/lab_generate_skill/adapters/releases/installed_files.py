"""Verify every installed byte using retained no-follow directory descriptors.

This is one verification traversal, not a cache or permission. Every requested
file is opened, hashed and checked again. All retained directory names are
checked before return, and every descriptor is closed on success or failure.
"""

import hashlib
import os
from pathlib import Path
import stat
from types import TracebackType
from typing import Literal
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from .artifact_copy import close_all
from .files import _stamp


class InstalledFileTraversal:
    def __init__(
        self,
        files: dict[Path, tuple[Path, ReleaseFile]],
        control: OperationControl,
    ) -> None:
        self.files, self.control = dict(files), control
        self.directories: dict[Path, int] = {}
        self.parents: dict[Path, tuple[int, str] | None] = {}
        self.closed = False
        self.entered = False

    def __enter__(self) -> "InstalledFileTraversal":
        if self.closed or self.entered:
            raise EvidenceIntegrityError("Installed traversal cannot reopen")
        self.control.checkpoint()
        self.entered = True
        return self

    def _directory(self, root: Path, path: Path) -> int:
        self.control.checkpoint()
        if self.closed:
            raise EvidenceIntegrityError("Installed traversal is closed")
        existing = self.directories.get(path)
        if existing is not None:
            return existing
        if not path.is_relative_to(root):
            raise EvidenceIntegrityError("Installed directory left declared root")
        parent: tuple[int, str] | None
        if path == root:
            if root.resolve(strict=True) != root:
                raise EvidenceIntegrityError("Installed root uses an alias")
            parent = None
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        else:
            parent = self._directory(root, path.parent), path.name
            fd = os.open(
                path.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent[0],
            )
        # Retain the descriptor before inspecting it, so every failure closes it.
        self.directories[path], self.parents[path] = fd, parent
        value = os.fstat(fd)
        if not stat.S_ISDIR(value.st_mode) or value.st_mode & 0o222:
            raise EvidenceIntegrityError("Installed directory is not readonly")
        return fd

    def verify(self, path: Path) -> None:
        self.control.checkpoint()
        if not self.entered or self.closed or path not in self.files:
            raise EvidenceIntegrityError("File is outside original installed roles")
        root, entry = self.files[path]
        if path != root / entry.path:
            raise EvidenceIntegrityError("Installed filename differs from pin")
        parent = self._directory(root, path.parent)
        fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent,
        )
        primary: BaseException | None = None
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_size != entry.size_bytes
                or before.st_mode & 0o222
                or bool(before.st_mode & 0o111) != entry.executable
            ):
                raise EvidenceIntegrityError("Installed file type/size/mode differs")
            digest, left = hashlib.sha256(), entry.size_bytes + 1
            while left:
                self.control.checkpoint()
                chunk = os.read(fd, min(left, 1024 * 1024))
                if not chunk:
                    break
                left -= len(chunk)
                digest.update(chunk)
            if left != 1 or digest.hexdigest() != entry.sha256:
                raise EvidenceIntegrityError("Installed file content differs")
            if _stamp(before) != _stamp(os.fstat(fd)) or _stamp(before) != _stamp(
                os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            ):
                raise EvidenceIntegrityError("Installed file changed during read")
            self.control.checkpoint()
        except BaseException as error:
            primary = error
            raise
        finally:
            close_all((fd,), primary)

    def _verify_directories(self) -> None:
        for path, fd in self.directories.items():
            self.control.checkpoint()
            parent = self.parents[path]
            current = (
                os.stat(path, follow_symlinks=False)
                if parent is None
                else os.stat(parent[1], dir_fd=parent[0], follow_symlinks=False)
            )
            held = os.fstat(fd)
            if (
                not stat.S_ISDIR(current.st_mode)
                or current.st_mode & 0o222
                or _stamp(current) != _stamp(held)
                or (parent is None and path.resolve(strict=True) != path)
            ):
                raise EvidenceIntegrityError("Installed directory binding changed")

    def __exit__(
        self,
        kind: type[BaseException] | None,
        primary: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        error = primary
        try:
            if primary is None:
                self._verify_directories()
                self.control.checkpoint()
        except BaseException as failure:
            error = failure
            raise
        finally:
            self.closed = True
            close_all(tuple(reversed(tuple(self.directories.values()))), error)
        return False
