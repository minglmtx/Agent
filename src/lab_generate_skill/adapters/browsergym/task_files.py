"""Stage exact public files, then execute unchanged native relative upload paths.

Only the isolated worker changes cwd. The original site private-root owner
removes files after browser closure; failed or uncertain preparation is never
retried. This is file delivery, not a website upload or a success assertion.
"""

import hashlib
import os
from pathlib import Path
import stat
import threading
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_task_files import (
    BrowserTaskFilesPlan,
    upload_paths,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import (
    copy_pinned_file,
    close_all,
)


class LocalBrowserTaskFiles:
    def __init__(self, plan: BrowserTaskFilesPlan) -> None:
        self.plan = BrowserTaskFilesPlan.model_validate_json(plan.model_dump_json())
        self.owner = os.getpid(), threading.get_ident()
        self.state = "new"
        self.previous: int | None = None
        self.directory: int | None = None
        self.identities: dict[str, tuple[int, int]] = {}

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Task files belong to the original browser worker/thread"
            )

    def prepare(self, spec: BrowserSessionSpec, control: OperationControl) -> None:
        self._owner()
        self.plan.check(spec)
        if self.state != "new":
            raise InvalidTransition(
                "Task file preparation is one-use, including partial failure"
            )
        control.checkpoint()
        self.state = "quarantined"
        root, source = Path(self.plan.staging_root), Path(self.plan.source.root)
        parent = root.parent
        info = parent.lstat()
        if (
            parent.resolve(strict=True) != parent
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or source.resolve(strict=True) != source
            or Path(self.plan.workspace_root).resolve(strict=True)
            != Path(self.plan.workspace_root)
        ):
            raise EvidenceIntegrityError(
                "Canonical owned private parent and workspace source required"
            )
        root.mkdir(mode=0o700)
        (root / "assets").mkdir(mode=0o700)
        for entry in self.plan.source.files:
            copy_pinned_file(source, root, entry, control)
            path = root / entry.path
            os.chmod(path, 0o400, follow_symlinks=False)
            value = path.lstat()
            self.identities[entry.path] = value.st_dev, value.st_ino
        self.previous = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
        self.directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        os.fchdir(self.directory)
        control.checkpoint()
        self.state = "ready"

    def validate(self, action: BrowserAction, control: OperationControl) -> None:
        self._owner()
        if self.state != "ready" or self.directory is None:
            raise InvalidTransition("Task files are not ready")
        control.checkpoint()
        cwd, expected = os.stat("."), os.fstat(self.directory)
        if (cwd.st_dev, cwd.st_ino) != (expected.st_dev, expected.st_ino):
            raise OwnershipConflict("Browser worker left its original file directory")
        for name in upload_paths(action):
            entry = next((e for e in self.plan.source.files if e.path == name), None)
            if entry is None:
                raise OwnershipConflict(
                    "Upload path is not a declared public logical file"
                )
            control.checkpoint()
            path = Path(self.plan.staging_root) / name
            if path.resolve(strict=True) != path:
                raise EvidenceIntegrityError("Upload file path uses an alias")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            primary: BaseException | None = None
            try:
                before = os.fstat(fd)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != os.getuid()
                    or before.st_nlink != 1
                    or before.st_mode & 0o377
                    or before.st_size != entry.size_bytes
                    or (before.st_dev, before.st_ino) != self.identities[name]
                ):
                    raise EvidenceIntegrityError(
                        "Upload file identity/type/size/permissions changed"
                    )
                digest = hashlib.sha256()
                remaining = entry.size_bytes + 1
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
                    or digest.hexdigest() != entry.sha256
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
                    raise EvidenceIntegrityError("Upload file bytes or stat changed")
            except BaseException as error:
                primary = error
                raise
            finally:
                close_all((fd,), primary)

    def close(self, control: OperationControl) -> None:
        self._owner()
        if self.state == "closed":
            return
        # Cwd restoration and descriptor closure are mandatory even after expiry.
        primary: BaseException | None = None
        try:
            if self.previous is not None:
                os.fchdir(self.previous)
        except BaseException as error:
            primary = error
            raise
        finally:
            previous, directory = self.previous, self.directory
            self.previous = self.directory = None
            self.state = "quarantined"
            close_all((directory, previous), primary)
            if primary is None:
                self.state = "closed"
