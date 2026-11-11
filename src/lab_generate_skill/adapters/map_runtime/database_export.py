"""Exclusive original runner program and complete immutable output readback."""

import hashlib
import os
from pathlib import Path
import stat
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.map_database_export import MapDatabaseExport
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.map_artifacts.files import (
    private_directory,
    write_once,
)
from lab_generate_skill.adapters.releases.artifact_copy import sync_directory, close_all
from .metadata import read_pinned_bytes


def roots(plan: MapDatabaseExport) -> Path:
    for path in (
        Path(plan.spec.inputs.files.node_root),
        Path(plan.spec.state_root("frontend")),
    ):
        private_directory(path)
    return Path(plan.host_directory)


def intent(plan: MapDatabaseExport) -> bytes:
    return plan.model_dump_json().encode()


def identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_uid,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


class NativeMapDatabaseExportFiles:
    def prepare(
        self, plan: MapDatabaseExport, program: bytes, control: OperationControl
    ) -> None:
        plan = MapDatabaseExport.model_validate(plan)
        if (
            type(program) is not bytes
            or len(program) != plan.program.size_bytes
            or hashlib.sha256(program).hexdigest() != plan.program.sha256
        ):
            raise EvidenceIntegrityError(
                "Native reference bytes differ from fixed program pin"
            )
        control.checkpoint()
        directory = roots(plan)
        directory.mkdir(mode=0o700)
        private_directory(directory)
        sync_directory(directory.parent)
        write_once(directory, "intent.json", intent(plan), control, readonly=True)
        written = write_once(directory, "reference.rb", program, control, readonly=True)
        if written != plan.program:
            raise EvidenceIntegrityError("Native program write changed original bytes")
        control.checkpoint()

    def read(self, plan: MapDatabaseExport, control: OperationControl) -> bytes:
        plan = MapDatabaseExport.model_validate(plan)
        directory = roots(plan)
        private_directory(directory)
        directory_identity = identity(directory.lstat())
        expected = {"intent.json", "reference.rb", plan.output_name}
        if {p.name for p in directory.iterdir()} != expected:
            raise EvidenceIntegrityError(
                "Complete exact native reference files required"
            )
        data = intent(plan)
        pin = ReleaseFile(
            path="intent.json",
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            executable=False,
        )
        if read_pinned_bytes(directory / pin.path, pin, control) != data:
            raise EvidenceIntegrityError("Native reference intent changed")
        read_pinned_bytes(directory / plan.program.path, plan.program, control)
        path = directory / plan.output_name
        fd: int | None = None
        primary: BaseException | None = None
        try:
            control.checkpoint()
            if path.resolve(strict=True) != path:
                raise EvidenceIntegrityError(
                    "Native reference output aliases another path"
                )
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o400
                or not 0 <= before.st_size <= plan.max_output_bytes
            ):
                raise EvidenceIntegrityError(
                    "Complete closed native reference type/mode/size required"
                )
            remaining = before.st_size + 1
            chunks = []
            while remaining:
                control.checkpoint()
                part = os.read(fd, min(1024 * 1024, remaining))
                if not part:
                    break
                chunks.append(part)
                remaining -= len(part)
            if (
                remaining != 1
                or identity(before) != identity(os.fstat(fd))
                or identity(before) != identity(path.lstat())
                or path.resolve(strict=True) != path
                or {p.name for p in directory.iterdir()} != expected
            ):
                raise EvidenceIntegrityError(
                    "Complete native reference identity/bytes changed"
                )
            if identity(directory.lstat()) != directory_identity:
                raise EvidenceIntegrityError(
                    "Native reference directory changed during read"
                )
            read_pinned_bytes(directory / plan.program.path, plan.program, control)
            if read_pinned_bytes(directory / pin.path, pin, control) != data:
                raise EvidenceIntegrityError(
                    "Native reference intent changed during read"
                )
            control.checkpoint()
            return b"".join(chunks)
        except BaseException as error:
            primary = error
            raise
        finally:
            close_all((fd,), primary)
