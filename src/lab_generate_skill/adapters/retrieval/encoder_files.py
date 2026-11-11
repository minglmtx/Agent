"""Verify an already staged immutable encoder tree before loading any code.

Bootstrap supplies the trusted local root. No download, path inference, repair or
copy occurs here. Deployment/staging owns isolation from concurrent file writers.
"""

import hashlib
import os
import stat
from pathlib import Path
from importlib.metadata import version

from lab_generate_skill.domain.encoding import EncoderFiles, EncoderConfig
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl


def verify_encoder(
    root: Path, files: EncoderFiles, config: EncoderConfig, control: OperationControl
) -> None:
    files = EncoderFiles.model_validate(files)
    config = EncoderConfig.model_validate(config)
    control.checkpoint()
    if not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir():
        raise EvidenceIntegrityError("Encoder root must be canonical staged directory")
    actual = []
    for path in sorted(root.rglob("*")):
        control.checkpoint()
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise EvidenceIntegrityError("Encoder contains nonregular member")
        actual.append(relative.as_posix())
    if actual != [f.path for f in files.files]:
        raise EvidenceIntegrityError("Encoder member set changed")
    for member in files.files:
        control.checkpoint()
        fd = os.open(root / member.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        primary: BaseException | None = None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise EvidenceIntegrityError("Encoder member changed type")
            digest = hashlib.sha256()
            size = 0
            while block := os.read(fd, 1024 * 1024):
                control.checkpoint()
                size += len(block)
                digest.update(block)
                if size > member.size_bytes:
                    raise EvidenceIntegrityError("Encoder member grew")
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                os.close(fd)
            except OSError as error:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Encoder verification and close failed", [primary, error]
                    ) from None
                raise
        if size != member.size_bytes or digest.hexdigest() != member.sha256:
            raise EvidenceIntegrityError("Encoder member digest changed")
    for package in config.packages:
        control.checkpoint()
        if version(package.name) != package.version:
            raise EvidenceIntegrityError(
                "Encoder package version changed: " + package.name
            )
