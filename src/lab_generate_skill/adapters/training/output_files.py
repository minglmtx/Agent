"""Worker-local complete native output pinning; no truncation, permission or writes."""

import hashlib
import os
from pathlib import Path
import stat
from lab_generate_skill.domain.training_output import TrainingOutputPlan
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.files import _inventory
from lab_generate_skill.adapters.releases.artifact_copy import close_all


def pin_training_output(
    plan: TrainingOutputPlan, control: OperationControl
) -> ReleaseArtifact:
    plan = TrainingOutputPlan.model_validate(plan)
    root = Path(plan.output_root)
    if (
        root.resolve(strict=True) != root
        or not root.is_dir()
        or root.lstat().st_uid != os.getuid()
    ):
        raise EvidenceIntegrityError(
            "Original owned canonical output directory required"
        )
    before = _inventory(root, control, require_readonly=False)
    if (
        not before
        or len(before) > plan.max_files
        or sum(s[2] for s in before.values()) > plan.max_total_bytes
    ):
        raise EvidenceIntegrityError("Complete output file set exceeds original budget")
    files = []
    for name in sorted(before):
        path = root / name
        if before[name][2] > plan.max_file_bytes or path.resolve(strict=True) != path:
            raise EvidenceIntegrityError(
                "Original output member exceeds bound or aliases another file"
            )
        fd: int | None = None
        primary: BaseException | None = None
        try:
            control.checkpoint()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            observed = os.fstat(fd)
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_uid != os.getuid()
                or observed.st_mode & 0o111
            ):
                raise EvidenceIntegrityError(
                    "Only owned nonexecutable native output files supported"
                )
            digest = hashlib.sha256()
            left = observed.st_size + 1
            while left:
                control.checkpoint()
                chunk = os.read(fd, min(left, 1024 * 1024))
                if not chunk:
                    break
                digest.update(chunk)
                left -= len(chunk)

            def identity(s: os.stat_result) -> tuple[int, ...]:
                return (
                    s.st_dev,
                    s.st_ino,
                    s.st_size,
                    s.st_mode,
                    s.st_mtime_ns,
                    s.st_ctime_ns,
                )

            if (
                left != 1
                or identity(observed) != identity(os.fstat(fd))
                or identity(observed) != identity(path.lstat())
                or path.resolve(strict=True) != path
            ):
                raise EvidenceIntegrityError(
                    "Native output bytes or identity changed while reading"
                )
            files.append(
                ReleaseFile(
                    path=name,
                    sha256=digest.hexdigest(),
                    size_bytes=observed.st_size,
                    executable=False,
                )
            )
        except BaseException as error:
            primary = error
            raise
        finally:
            close_all((fd,), primary)
    if before != _inventory(root, control, require_readonly=False):
        raise EvidenceIntegrityError("Native output inventory changed while capturing")
    return ReleaseArtifact(
        artifact_id="sft-source-"
        + hashlib.sha256(plan.training.training_id.encode()).hexdigest(),
        root=str(root),
        files=tuple(files),
    )
