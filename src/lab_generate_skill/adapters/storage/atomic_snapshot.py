"""One bounded byte snapshot transaction on a pre-existing trusted directory.

This adapter owns stable flock/read/replace/fsync and all descriptor cleanup.
Domain JSON/schema and authority checks belong to its caller. A post-publication
error may leave a complete new snapshot; exceptions never prove non-commit.
"""

from __future__ import annotations

import fcntl
import os
import re
import stat
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl


def _close(descriptors: tuple[int | None, ...], primary: BaseException | None) -> None:
    errors: list[Exception] = []
    for fd in descriptors:
        if fd is not None:
            try:
                os.close(fd)
            except OSError as error:
                errors.append(error)
    if errors:
        if primary is not None:
            raise BaseExceptionGroup(
                "Snapshot operation and close failed", [primary, *errors]
            ) from None
        raise ExceptionGroup("Snapshot close failed", errors)


class AtomicSnapshotFile:
    def __init__(self, root: Path, name: str, *, max_bytes: int) -> None:
        if type(name) is not str or (
            name != "system-current.json"
            and re.fullmatch(r"[0-9a-f]{64}\.[a-z-]+\.json", name) is None
        ):
            raise ValueError(
                "Snapshot needs a hashed namespace or the fixed system-current.json name"
            )
        if type(max_bytes) is not int or not 1 <= max_bytes <= 8 * 1024 * 1024:
            raise ValueError("Snapshot size bound must be an integer in [1, 8 MiB]")
        self.root, self.name, self.max_bytes = root, name, max_bytes

    @contextmanager
    def locked(
        self, control: OperationControl, *, create_lock: bool = True
    ) -> Iterator[SnapshotTransaction]:
        if type(create_lock) is not bool:
            raise TypeError("create_lock must be a bool")
        control.checkpoint()
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        lock: int | None = None
        handle: SnapshotTransaction | None = None
        primary: BaseException | None = None
        try:
            try:
                flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
                try:
                    lock = os.open(self.name + ".lock", flags, dir_fd=directory)
                except FileNotFoundError:
                    if not create_lock:
                        raise
                    # A missing lock for retained history must never become a
                    # second lock while an old writer owns the original inode.
                    used = any(
                        name == self.name
                        or (
                            name.startswith(self.name + ".")
                            and name != self.name + ".lock"
                        )
                        for name in os.listdir(directory)
                    )
                    control.checkpoint()
                    # A concurrent first creator may already have established
                    # the original lock; reopen it, but never create if used.
                    lock = os.open(
                        self.name + ".lock",
                        flags | (0 if used else os.O_CREAT),
                        0o600,
                        dir_fd=directory,
                    )
            except OSError as error:
                raise EvidenceIntegrityError("Unsafe snapshot lock") from error
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise EvidenceIntegrityError("Snapshot lock must be a regular file")
            while True:
                control.checkpoint()
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    control.wait(0.02)
            handle = SnapshotTransaction(self, directory, lock, control)
            handle.checkpoint()
            yield handle
        except BaseException as error:
            primary = error
            raise
        finally:
            if handle is not None:
                handle.active = False
            _close((lock, directory), primary)


class SnapshotTransaction:
    """Handle valid only inside locked() and its original process/thread."""

    _MARKER = b"atomic-snapshot/1\n"

    def __init__(
        self,
        file: AtomicSnapshotFile,
        directory: int,
        lock: int,
        control: OperationControl,
    ) -> None:
        self.file, self.directory, self.lock, self.control = (
            file,
            directory,
            lock,
            control,
        )
        self.process, self.thread, self.active = (
            os.getpid(),
            threading.get_ident(),
            True,
        )

    def checkpoint(self) -> None:
        if not self.active or (self.process, self.thread) != (
            os.getpid(),
            threading.get_ident(),
        ):
            raise OwnershipConflict("Expired or foreign snapshot transaction")
        self.control.checkpoint()
        opened = os.fstat(self.lock)
        try:
            current = os.stat(
                self.file.name + ".lock", dir_fd=self.directory, follow_symlinks=False
            )
        except OSError as error:
            raise OwnershipConflict("Stable snapshot lock disappeared") from error
        if not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise OwnershipConflict("Stable snapshot lock was replaced")

    def _initialized(self) -> bool:
        try:
            fd = os.open(
                self.file.name + ".initialized",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self.directory,
            )
        except FileNotFoundError:
            return False
        except OSError as error:
            raise EvidenceIntegrityError(
                "Unsafe snapshot initialization marker"
            ) from error
        primary: BaseException | None = None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise EvidenceIntegrityError(
                    "Initialization marker must be a regular file"
                )
            raw = bytearray()
            while len(raw) <= len(self._MARKER):
                chunk = os.read(fd, len(self._MARKER) + 1 - len(raw))
                if not chunk:
                    break
                raw.extend(chunk)
            if raw != self._MARKER:
                raise EvidenceIntegrityError("Invalid snapshot initialization marker")
            return True
        except BaseException as error:
            primary = error
            raise
        finally:
            _close((fd,), primary)

    def _initialize(self) -> None:
        # Durable before first publication. If publication then fails, absence is
        # deliberately ambiguous and cannot silently reopen an empty budget.
        fd = os.open(
            self.file.name + ".initialized",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.directory,
        )
        primary: BaseException | None = None
        try:
            offset = 0
            while offset < len(self._MARKER):
                count = os.write(fd, self._MARKER[offset:])
                if count <= 0:
                    raise OSError("Initialization marker write made no progress")
                offset += count
            os.fsync(fd)
            os.fsync(self.directory)
        except BaseException as error:
            primary = error
            raise
        finally:
            _close((fd,), primary)

    def pending_keys(self) -> tuple[str, ...]:
        """Spending fences, not a second accounting history; caller owns meaning."""
        self.checkpoint()
        prefix = self.file.name + ".pending-"
        keys: list[str] = []
        for name in os.listdir(self.directory):
            self.checkpoint()
            if name.startswith(prefix):
                key = name[len(prefix) :]
                if re.fullmatch("[0-9a-f]{64}", key) is None:
                    raise EvidenceIntegrityError("Malformed pending snapshot marker")
                keys.append(key)
        return tuple(sorted(keys))

    def pending(self, key: str) -> bytes | None:
        self.checkpoint()
        if re.fullmatch("[0-9a-f]{64}", key) is None:
            raise ValueError("Pending key must be a digest")
        try:
            fd = os.open(
                self.file.name + ".pending-" + key,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self.directory,
            )
        except FileNotFoundError:
            return None
        except OSError as error:
            raise EvidenceIntegrityError("Unsafe pending snapshot marker") from error
        primary: BaseException | None = None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise EvidenceIntegrityError("Pending marker must be a regular file")
            parts: list[bytes] = []
            left = 8193
            while left:
                chunk = os.read(fd, left)
                if not chunk:
                    break
                parts.append(chunk)
                left -= len(chunk)
            raw = b"".join(parts)
            if not raw or len(raw) > 8192:
                raise EvidenceIntegrityError("Pending marker payload is invalid")
            return raw
        except BaseException as error:
            primary = error
            raise
        finally:
            _close((fd,), primary)

    def retain_pending(self, key: str, raw: bytes) -> None:
        self.checkpoint()
        if type(raw) is not bytes or not 1 <= len(raw) <= 8192:
            raise ValueError("Pending reference must be bounded bytes")
        prior = self.pending(key)
        if prior is not None:
            if prior != raw:
                raise OwnershipConflict(
                    "Pending digest is already bound to another reference"
                )
            return
        fd = os.open(
            self.file.name + ".pending-" + key,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.directory,
        )
        primary: BaseException | None = None
        try:
            offset = 0
            while offset < len(raw):
                self.checkpoint()
                count = os.write(fd, raw[offset:])
                if count <= 0:
                    raise OSError("Pending marker write made no progress")
                offset += count
            os.fsync(fd)
            os.fsync(self.directory)
        except BaseException as error:
            primary = error
            raise
        finally:
            _close((fd,), primary)

    def resolve_pending(self, key: str, expected: bytes) -> None:
        self.checkpoint()
        prior = self.pending(key)
        if prior is None:
            return
        if prior != expected:
            raise OwnershipConflict("Pending marker changed before resolution")
        os.unlink(self.file.name + ".pending-" + key, dir_fd=self.directory)
        os.fsync(self.directory)
        self.checkpoint()

    def read(self) -> bytes | None:
        self.checkpoint()
        initialized = self._initialized()
        try:
            fd = os.open(
                self.file.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self.directory,
            )
        except FileNotFoundError:
            if initialized:
                raise EvidenceIntegrityError(
                    "Initialized snapshot is missing; reconcile original history"
                )
            return None
        except OSError as error:
            raise EvidenceIntegrityError("Unsafe snapshot") from error
        primary: BaseException | None = None
        try:
            if not initialized:
                raise EvidenceIntegrityError("Snapshot has no initialization marker")
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise EvidenceIntegrityError("Snapshot must be a regular file")
            chunks: list[bytes] = []
            left = self.file.max_bytes + 1
            while left:
                self.checkpoint()
                chunk = os.read(fd, min(left, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                left -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > self.file.max_bytes:
                raise EvidenceIntegrityError("Snapshot exceeds its byte limit")
            self.checkpoint()
            return raw
        except BaseException as error:
            primary = error
            raise
        finally:
            _close((fd,), primary)

    def confirm(self) -> None:
        """Sync an existing snapshot and directory after an uncertain commit.

        Readback alone is not durability confirmation. Caller validates original
        bytes under this same lock before confirming; this never rewrites them.
        """
        self.checkpoint()
        if self.read() is None:
            raise EvidenceIntegrityError("Cannot confirm an absent snapshot")
        fd = os.open(
            self.file.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=self.directory,
        )
        primary: BaseException | None = None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise EvidenceIntegrityError("Snapshot must be a regular file")
            os.fsync(fd)
            os.fsync(self.directory)
            self.checkpoint()
        except BaseException as error:
            primary = error
            raise
        finally:
            _close((fd,), primary)

    def write(self, raw: bytes) -> None:
        if type(raw) is not bytes or len(raw) > self.file.max_bytes:
            raise ValueError("Snapshot payload must be bounded immutable bytes")
        self.checkpoint()
        if self.read() is None:
            self._initialize()
        temporary = ".pending-snapshot-" + uuid.uuid4().hex
        fd: int | None = None
        created = False
        primary: BaseException | None = None
        try:
            fd = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
                dir_fd=self.directory,
            )
            created = True
            view, offset = memoryview(raw), 0
            while offset < len(view):
                self.checkpoint()
                written = os.write(fd, view[offset:])
                if written <= 0:
                    raise OSError("Snapshot write made no progress")
                offset += written
            os.fsync(fd)
            self.checkpoint()
            os.replace(
                temporary,
                self.file.name,
                src_dir_fd=self.directory,
                dst_dir_fd=self.directory,
            )
            created = False
            os.fsync(self.directory)
            self.checkpoint()
        except BaseException as error:
            primary = error
            raise
        finally:
            cleanup: BaseException | None = primary
            try:
                if created:
                    try:
                        os.unlink(temporary, dir_fd=self.directory)
                    except FileNotFoundError:
                        pass
                    except OSError as error:
                        if primary is not None:
                            cleanup = BaseExceptionGroup(
                                "Snapshot write and temporary cleanup failed",
                                [primary, error],
                            )
                        else:
                            cleanup = error
                        raise cleanup from None
            finally:
                _close((fd,), cleanup)
