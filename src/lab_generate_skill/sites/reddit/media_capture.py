"""Fresh original native media bytes/metadata, outside public role observations."""

import hashlib
import os
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .native_schema import NativeMedia, MediaFile
from .service_contract import RedditServiceSpec


class NativeMediaCapture:
    def __init__(self, spec: RedditServiceSpec) -> None:
        self.spec = RedditServiceSpec.model_validate_json(spec.model_dump_json())

    def capture(self, control: OperationControl) -> NativeMedia:
        from PIL import Image

        root = Path(self.spec.files.state_root) / "media-native"
        if root.resolve(strict=True) != root or not root.is_dir():
            raise EvidenceIntegrityError("Original native media directory required")
        directories: list[str] = []
        files: dict[str, MediaFile] = {}
        paths = sorted(root.rglob("*"))
        if len(paths) > 100000:
            raise EvidenceIntegrityError("Complete native media entry bound exceeded")
        for path in paths:
            control.checkpoint()
            info = path.lstat()
            name = path.relative_to(root).as_posix()
            if stat.S_ISLNK(info.st_mode):
                raise EvidenceIntegrityError("Native media symlink is not authorized")
            if stat.S_ISDIR(info.st_mode):
                directories.append(name)
                continue
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.getuid()
            ):
                raise EvidenceIntegrityError(
                    "Native media must be an original owned regular file"
                )
            if info.st_size > 64 * 1024**2:
                raise EvidenceIntegrityError(
                    "Native media file exceeds bounded capture"
                )
            if path.resolve(strict=True) != path:
                raise EvidenceIntegrityError("Native media path changed alias")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            primary: BaseException | None = None
            try:
                before = os.fstat(fd)
                if (
                    before.st_dev,
                    before.st_ino,
                    before.st_mode,
                    before.st_nlink,
                    before.st_uid,
                    before.st_size,
                ) != (
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    info.st_nlink,
                    info.st_uid,
                    info.st_size,
                ):
                    raise EvidenceIntegrityError("Native media file identity changed")
                digest = hashlib.sha256()
                remaining = before.st_size + 1
                while remaining:
                    control.checkpoint()
                    chunk = os.read(fd, min(1024**2, remaining))
                    if not chunk:
                        break
                    digest.update(chunk)
                    remaining -= len(chunk)
                image_format = None
                dimensions = None
                if path.suffix.lower() in (".jpg", ".jpeg"):
                    os.lseek(fd, 0, os.SEEK_SET)
                    with os.fdopen(os.dup(fd), "rb") as stream:
                        with Image.open(stream) as image:
                            image.verify()
                    os.lseek(fd, 0, os.SEEK_SET)
                    with os.fdopen(os.dup(fd), "rb") as stream:
                        with Image.open(stream) as image:
                            image_format = image.format
                            dimensions = image.size
                after = os.fstat(fd)
                if remaining != 1 or (
                    before.st_dev,
                    before.st_ino,
                    before.st_mode,
                    before.st_nlink,
                    before.st_uid,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                ) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_mode,
                    after.st_nlink,
                    after.st_uid,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                ):
                    raise EvidenceIntegrityError(
                        "Native media bytes changed during capture"
                    )
                files[name] = MediaFile(
                    bytes=before.st_size,
                    sha256=digest.hexdigest(),
                    format=image_format,
                    dimensions=dimensions,
                )
            except BaseException as error:
                primary = error
                raise
            finally:
                try:
                    os.close(fd)
                except OSError as error:
                    if primary is not None:
                        raise BaseExceptionGroup(
                            "Native media capture and descriptor close failed",
                            [primary, error],
                        ) from None
                    raise
        return NativeMedia(
            version="reddit-native-media-storage-candidate-v2",
            directories=tuple(directories),
            files=files,
        )
