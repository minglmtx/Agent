"""Atomic, content-addressed filesystem implementation of EvidenceStore.

Input: trusted store root, bytes and typed metadata. Output: cas://sha256 refs.
Writes fsync a temporary inode before an atomic create-only link; concurrent
identical writers converge, corrupt existing objects are never replaced.
Directory descriptors and O_NOFOLLOW prevent reference-driven path traversal.
Runtime owns root placement, permissions, quotas, deadlines and archiving;
this synchronous adapter is intended for bounded per-stage evidence objects.

This synchronous implementation is a worker-internal primitive. It does not
implement the controlled production EvidenceStore port; the enclosing worker
must be supervised. Production consumers must not use it as a fallback.
"""

import hashlib
import os
import stat
import uuid
from pathlib import Path

from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from .temporary_identity import exchange_temporary_name


class FileEvidenceStore:
    """One root holds immutable blobs; metadata accompanies each reference."""

    def __init__(
        self,
        root: Path,
        *,
        max_object_bytes: int = 64 * 1024 * 1024,
        initialize: bool = True,
    ) -> None:
        if type(max_object_bytes) is not int or max_object_bytes <= 0:
            raise ValueError("A positive object size limit is required")
        if type(initialize) is not bool:
            raise TypeError("Storage initialization choice must be boolean")
        self._limit = max_object_bytes
        self._blobs = root / "blobs"
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if initialize:
                try:
                    os.mkdir("blobs", mode=0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
                os.fsync(root_fd)
        finally:
            os.close(root_fd)

    def _directory(self) -> int:
        try:
            return os.open(self._blobs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as error:
            raise EvidenceIntegrityError(
                "Evidence directory is unavailable or unsafe"
            ) from error

    def _read(self, directory: int, name: str) -> bytes:
        try:
            fd = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
        except FileNotFoundError as error:
            raise EvidenceNotFound("Evidence object is absent") from error
        except OSError as error:
            raise EvidenceIntegrityError(
                "Evidence object cannot be safely opened"
            ) from error
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise EvidenceIntegrityError("Evidence object must be a regular file")
            if os.fstat(stream.fileno()).st_size > self._limit:
                raise EvidenceIntegrityError("Evidence exceeds configured object limit")
            data = stream.read(self._limit + 1)
            if len(data) > self._limit:
                raise EvidenceIntegrityError(
                    "Evidence grew beyond configured object limit"
                )
            return data

    def put(
        self,
        data: bytes,
        metadata: EvidenceMetadata,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        """Validate before effects; publish once, retaining primary/cleanup errors.

        A post-link error can leave a complete blob: reconcile identical bytes,
        never infer non-commit from an exception. Cleanup groups list the primary
        error first, followed by each failed cleanup in attempted order.
        """
        if type(data) is not bytes:
            raise TypeError("Evidence payload must be immutable bytes")
        if not isinstance(metadata, EvidenceMetadata):
            raise TypeError("Evidence metadata must be EvidenceMetadata")
        metadata = EvidenceMetadata.model_validate(metadata)
        if len(data) > self._limit:
            raise EvidenceIntegrityError("Evidence exceeds configured object limit")
        reference = evidence_reference(data, metadata)
        digest = reference.sha256
        # Worker calls always bind the original exchange. Standalone primitive
        # callers use private random scratch; neither mode authorizes replay.
        temporary = (
            ".pending-" + uuid.uuid4().hex
            if exchange_id is None
            else exchange_temporary_name(exchange_id)
        )
        directory = self._directory()
        fd: int | None = None
        primary_error: BaseException | None = None
        try:
            fd = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                mode=0o600,
                dir_fd=directory,
            )
            # Own the descriptor explicitly so close failures cannot replace a
            # write failure through a stream context manager's __exit__.
            view = memoryview(data)
            offset = 0
            while offset < len(view):
                written = os.write(fd, view[offset:])
                if written <= 0:
                    raise OSError("Evidence write made no progress")
                offset += written
            os.fsync(fd)
            try:
                os.link(
                    temporary,
                    digest,
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                    follow_symlinks=False,
                )
            except FileExistsError:
                if self._read(directory, digest) != data:
                    raise EvidenceIntegrityError(
                        "Existing evidence differs; refusing overwrite"
                    ) from None
            os.fsync(directory)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            cleanup_errors: list[Exception] = []
            if fd is not None:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
                except OSError as error:
                    cleanup_errors.append(error)
            for descriptor in (fd, directory):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError as error:
                        cleanup_errors.append(error)
            if cleanup_errors:
                if primary_error is not None:
                    raise BaseExceptionGroup(
                        "Evidence write and cleanup failed",
                        [primary_error, *cleanup_errors],
                    ) from None
                raise ExceptionGroup("Evidence write cleanup failed", cleanup_errors)
        return reference

    def read(self, reference: EvidenceRef) -> bytes:
        """Validate location, digest and size before exposing bytes to consumers."""
        if reference.uri != f"cas://sha256/{reference.sha256}":
            raise EvidenceIntegrityError(
                "Reference does not identify this store's CAS object"
            )
        directory = self._directory()
        try:
            return self._read_verified(directory, reference)
        finally:
            os.close(directory)

    def _read_verified(self, directory: int, reference: EvidenceRef) -> bytes:
        """Worker-internal read using an already owned, pinned blobs descriptor."""
        data = self._read(directory, reference.sha256)
        if (
            len(data) != reference.size_bytes
            or hashlib.sha256(data).hexdigest() != reference.sha256
        ):
            raise EvidenceIntegrityError("Evidence digest or size does not match")
        return data
