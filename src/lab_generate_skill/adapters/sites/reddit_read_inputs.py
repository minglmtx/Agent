"""One owned local immutable native selector artifact; original resource admits I/O.

The payload is private under this instance, mounted readonly only for native
reads. No partial file is adopted, unknown publication is never repeated.
"""

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import threading
from lab_generate_skill.domain.reddit_native_read_input import (
    MAX_BASELINE_BYTES,
    BaselineIdsPayload,
    BaselineIdsRef,
    BaselineIdsUnconfirmed,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    EvidenceIntegrityError,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import close_all, sync_directory


class NativeReadInputs:
    def __init__(self, input_root: str) -> None:
        if type(input_root) is not str:
            raise ValueError("Native input root must be a canonical private node path")
        path = PurePosixPath(input_root)
        if (
            not path.is_absolute()
            or str(path) != input_root
            or not path.is_relative_to("/tmp")
            or len(path.parts) < 4
            or path.name != "native-input"
            or ".." in path.parts
            or any(c in input_root for c in ("\0", "\\", ":", ",", "\n", "\r"))
        ):
            raise ValueError("Native input root must be an original private node child")
        self.input_root = Path(input_root)
        self.owner = os.getpid(), threading.get_ident()
        self.attempted = False
        self.result: BaselineIdsRef | None = None
        self.identity: tuple[int, int] | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Native read inputs belong to original worker/thread"
            )

    def publish(
        self,
        request: SiteTaskRequest,
        ranges: tuple[tuple[int, int], ...],
        count: int,
        control: OperationControl,
    ) -> BaselineIdsRef:
        self._owner()
        request = SiteTaskRequest.model_validate_json(request.model_dump_json())
        if request.action != "snapshot" or request.task.site != "reddit":
            raise ValueError("Original Reddit snapshot request required")
        value = BaselineIdsPayload(
            task=request.task, request_sha256=request.digest, count=count, ranges=ranges
        )
        raw = value.model_dump_json().encode()
        if not 0 < len(raw) <= MAX_BASELINE_BYTES:
            raise ValueError("Native baseline artifact exceeds byte bound")
        if self.attempted:
            raise InvalidTransition(
                "Native baseline input publication is one-use, including failure"
            )
        control.checkpoint()
        self.attempted = True
        root = self.input_root
        if root.parent.resolve(strict=True) != root.parent:
            raise EvidenceIntegrityError("Native input parent uses an alias")
        info = root.parent.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise EvidenceIntegrityError("Owned private native input parent required")
        root.mkdir(mode=0o700)
        filename = request.digest + ".json"
        path = root / filename
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        primary: BaseException | None = None
        try:
            view = memoryview(raw)
            while view:
                control.checkpoint()
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("Native baseline write made no progress")
                view = view[written:]
            os.fchmod(fd, 0o400)
            os.fsync(fd)
            value_stat = os.fstat(fd)
            self.identity = value_stat.st_dev, value_stat.st_ino
        except BaseException as error:
            primary = error
            raise
        finally:
            close_all((fd,), primary)
        sync_directory(root)
        self.result = BaselineIdsRef(
            task=request.task,
            request_sha256=request.digest,
            filename=filename,
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
        )
        try:
            control.checkpoint()
        except Exception as error:
            raise BaselineIdsUnconfirmed(self.result) from error
        return self.result

    def verify(self, reference: BaselineIdsRef, control: OperationControl) -> None:
        self._owner()
        reference = BaselineIdsRef.model_validate_json(reference.model_dump_json())
        if reference != self.result or self.identity is None:
            raise OwnershipConflict("Unknown or foreign original native baseline input")
        control.checkpoint()
        path = self.input_root / reference.filename
        if path.resolve(strict=True) != path:
            raise EvidenceIntegrityError("Native baseline input uses an alias")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        primary: BaseException | None = None
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink != 1
                or before.st_mode & 0o777 != 0o400
                or before.st_size != reference.size_bytes
                or (before.st_dev, before.st_ino) != self.identity
            ):
                raise EvidenceIntegrityError(
                    "Native baseline input identity/type/permissions changed"
                )
            digest = hashlib.sha256()
            remaining = reference.size_bytes + 1
            while remaining:
                control.checkpoint()
                chunk = os.read(fd, min(1024**2, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
            after = os.fstat(fd)
            if (
                remaining != 1
                or digest.hexdigest() != reference.sha256
                or (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                )
                != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                )
            ):
                raise EvidenceIntegrityError("Native baseline input bytes changed")
        except BaseException as error:
            primary = error
            raise
        finally:
            close_all((fd,), primary)
