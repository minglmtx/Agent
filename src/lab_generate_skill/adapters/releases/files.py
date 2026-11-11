"""Read-only frozen artifact verification, entirely inside external supervision.

All declared regular files, sizes, hashes and executable modes must match; no
extra files, symlinks, writable files or implicit dependency discovery. Trusted
workspace root is supplied by bootstrap, never taken from the manifest. This
proves file identity only, not compatibility, caller permission or deployment.
"""

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.domain.release import (
    ReleaseManifest,
    ReleaseFile,
    ReleaseArtifact,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl


@dataclass(frozen=True)
class VerifiedReleaseFiles:
    release_id: str
    manifest_sha256: str
    artifact_ids: tuple[str, ...]
    file_count: int
    byte_count: int


def _stamp(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_mode


def _file(root: Path, entry: ReleaseFile, control: OperationControl) -> None:
    path = root / entry.path
    if path.resolve(strict=True) != path:
        raise EvidenceIntegrityError("Release file uses a symlink alias")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    primary: BaseException | None = None
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size != entry.size_bytes
            or before.st_mode & 0o222
            or bool(before.st_mode & 0o111) != entry.executable
        ):
            raise EvidenceIntegrityError("Release file type/size/mode differs")
        digest = hashlib.sha256()
        left = entry.size_bytes + 1
        while left:
            control.checkpoint()
            chunk = os.read(fd, min(left, 1024 * 1024))
            if not chunk:
                break
            left -= len(chunk)
            digest.update(chunk)
        if left != 1 or digest.hexdigest() != entry.sha256:
            raise EvidenceIntegrityError("Release file content differs")
        if (
            _stamp(before) != _stamp(os.fstat(fd))
            or _stamp(before) != _stamp(path.stat(follow_symlinks=False))
            or path.resolve(strict=True) != path
        ):
            raise EvidenceIntegrityError("Release file changed during verification")
        control.checkpoint()
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            os.close(fd)
        except OSError as error:
            if primary is not None:
                raise BaseExceptionGroup(
                    "Release verification and close failed", [primary, error]
                ) from None
            raise


def _inventory(
    root: Path, control: OperationControl, *, require_readonly: bool = True
) -> dict[str, tuple[int, int, int, int, int]]:
    found: dict[str, tuple[int, int, int, int, int]] = {}
    scanned = 0

    def fail(error: OSError) -> None:
        raise error

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        control.checkpoint()
        scanned += len(dirs) + len(files)
        if scanned > 200000:
            raise EvidenceIntegrityError("Release directory inventory exceeds budget")
        if require_readonly and Path(directory).stat().st_mode & 0o222:
            raise EvidenceIntegrityError("Release directory is writable")
        file_names = set(files)
        for name in dirs + files:
            path = Path(directory) / name
            value = path.lstat()
            if stat.S_ISLNK(value.st_mode) or not (
                stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode)
            ):
                raise EvidenceIntegrityError("Release contains a link or special file")
            if name in file_names:
                # Retain the same no-follow observation whose type was checked.
                # The final inventory remains an independent fresh traversal.
                found[str(path.relative_to(root))] = _stamp(value)
        if len(found) > 100000:
            raise EvidenceIntegrityError("Release inventory exceeds file budget")
    return found


def verify_release_files(
    manifest: ReleaseManifest, workspace_root: Path, control: OperationControl
) -> VerifiedReleaseFiles:
    manifest = ReleaseManifest.model_validate(manifest)
    if not isinstance(workspace_root, Path) or not workspace_root.is_absolute():
        raise ValueError("Trusted workspace root must be absolute")
    control.checkpoint()
    workspace = workspace_root.resolve(strict=True)
    if workspace != workspace_root or not workspace.is_dir():
        raise EvidenceIntegrityError("Workspace root must be a canonical directory")
    total_files = total_bytes = 0
    snapshots: dict[
        Path,
        tuple[
            tuple[int, int, int, int, int], dict[str, tuple[int, int, int, int, int]]
        ],
    ] = {}
    for artifact in manifest.artifacts:
        root = Path(artifact.root)
        if (
            root == workspace
            or not root.is_relative_to(workspace)
            or root.resolve(strict=True) != root
            or not root.is_dir()
        ):
            raise EvidenceIntegrityError("Artifact root escapes canonical workspace")
        before = root.stat()
        expected = {entry.path for entry in artifact.files}
        inventory = _inventory(root, control)
        snapshots[root] = (_stamp(before), inventory)
        if set(inventory) != expected:
            raise EvidenceIntegrityError("Release file inventory differs")
        for entry in artifact.files:
            _file(root, entry, control)
            total_files += 1
            total_bytes += entry.size_bytes
        after = root.stat()
        if _stamp(before) != _stamp(after) or _inventory(root, control) != inventory:
            raise EvidenceIntegrityError("Release artifact changed during verification")
    # Shared filesystems may report only whole-second timestamps. Metadata
    # equality cannot substitute for rechecking previously observed bytes.
    for artifact in manifest.artifacts:
        for entry in artifact.files:
            _file(Path(artifact.root), entry, control)
    for root, (root_stamp, inventory) in snapshots.items():
        if _stamp(root.stat()) != root_stamp or _inventory(root, control) != inventory:
            raise EvidenceIntegrityError("Release changed during final content pass")
    control.checkpoint()
    return VerifiedReleaseFiles(
        manifest.release_id,
        hashlib.sha256(manifest.model_dump_json().encode()).hexdigest(),
        tuple(a.artifact_id for a in manifest.artifacts),
        total_files,
        total_bytes,
    )


def verify_artifact(artifact: ReleaseArtifact, control: OperationControl) -> None:
    """Verify one complete immutable staged artifact; no workspace assumption."""
    artifact = ReleaseArtifact.model_validate(artifact)
    control.checkpoint()
    root = Path(artifact.root)
    if (
        root.resolve(strict=True) != root
        or not root.is_dir()
        or root.stat().st_mode & 0o222
    ):
        raise EvidenceIntegrityError(
            "Frozen artifact root is not canonical and read-only"
        )
    before = _inventory(root, control)
    if set(before) != {entry.path for entry in artifact.files}:
        raise EvidenceIntegrityError("Frozen artifact file set differs")
    for _ in range(2):
        for entry in artifact.files:
            _file(root, entry, control)
    if _inventory(root, control) != before:
        raise EvidenceIntegrityError("Frozen artifact changed during verification")
