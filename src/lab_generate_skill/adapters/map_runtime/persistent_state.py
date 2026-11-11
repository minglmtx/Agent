"""Full private frontend hashes and pinned geographic baseline, no DB execution."""

import hashlib
import os
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.map_state import MapPersistentState
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.releases.artifact_copy import close_all
from lab_generate_skill.adapters.map_artifacts.files import private_directory
from .read_inputs import PublishedMapInputs
from .metadata import read_pinned_bytes


def identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def scan(root: Path, control: OperationControl) -> dict[str, tuple[int, ...]]:
    entries = {}
    pending = [root / "storage", root / "public"]
    for path in pending:
        private_directory(path)
    while pending:
        control.checkpoint()
        path = pending.pop()
        info = path.lstat()
        if (
            path.resolve(strict=True) != path
            or info.st_uid != os.getuid()
            or not (
                stat.S_ISDIR(info.st_mode)
                or stat.S_ISREG(info.st_mode)
                and info.st_nlink == 1
            )
        ):
            raise EvidenceIntegrityError(
                "Unexpected alias/type/owner in Map persistent files"
            )
        entries[str(path.relative_to(root))] = identity(info)
        if len(entries) > 100000:
            raise EvidenceIntegrityError(
                "Complete Map persistent inventory exceeds bound"
            )
        if stat.S_ISDIR(info.st_mode):
            pending.extend(path.iterdir())
    return entries


def file_pin(
    root: Path, name: str, expected: tuple[int, ...], control: OperationControl
) -> ReleaseFile:
    path = root / name
    fd: int | None = None
    primary: BaseException | None = None
    try:
        control.checkpoint()
        if path.resolve(strict=True) != path:
            raise EvidenceIntegrityError(
                "Original Map persistent file aliases another path"
            )
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or identity(before) != expected
            or not 0 <= before.st_size <= 2 * 1024**4
        ):
            raise EvidenceIntegrityError(
                "Original Map persistent file identity differs"
            )
        digest = hashlib.sha256()
        remaining = before.st_size + 1
        while remaining:
            control.checkpoint()
            part = os.read(fd, min(1024 * 1024, remaining))
            if not part:
                break
            digest.update(part)
            remaining -= len(part)
        if (
            remaining != 1
            or identity(os.fstat(fd)) != expected
            or identity(path.lstat()) != expected
            or path.resolve(strict=True) != path
        ):
            raise EvidenceIntegrityError(
                "Map persistent bytes/identity changed during capture"
            )
        return ReleaseFile(
            path=name,
            sha256=digest.hexdigest(),
            size_bytes=before.st_size,
            executable=bool(before.st_mode & 0o111),
        )
    except BaseException as error:
        primary = error
        raise
    finally:
        close_all((fd,), primary)


class NativeMapPersistentFiles:
    def capture(
        self, spec: MapServiceSpec, control: OperationControl
    ) -> MapPersistentState:
        spec = MapServiceSpec.model_validate(spec)
        private_directory(Path(spec.inputs.files.node_root))
        root = Path(spec.inputs.node_tree("frontend"))
        private_directory(root)
        inventories = PublishedMapInputs().read(spec.inputs, control)
        app = next(i for i in inventories if i.role == "app")
        pin = next(m.file for m in app.files if m.file.path == "baseline.json")
        baseline = read_pinned_bytes(
            Path(spec.inputs.node_tree("app")) / "baseline.json", pin, control
        )
        before = scan(root, control)
        names = [n for n, i in before.items() if stat.S_ISREG(i[2])]
        ordered = sorted(n for n in names if n.startswith("storage/")) + sorted(
            n for n in names if n.startswith("public/")
        )
        files = tuple(file_pin(root, n, before[n], control) for n in ordered)
        if scan(root, control) != before:
            raise EvidenceIntegrityError(
                "Complete Map persistent tree changed during capture"
            )
        control.checkpoint()
        return MapPersistentState(baseline_json=baseline.decode("utf-8"), files=files)
