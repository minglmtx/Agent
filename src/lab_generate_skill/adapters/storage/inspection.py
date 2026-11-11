"""Inspect one original CAS exchange without repairing or deleting anything.

Run the WHOLE function inside outer process supervision: path resolution, open,
read, hash, stat and close are synchronous filesystem operations. The caller
must bind the observed root to its real storage authority and separately prove
original-worker termination. A known temporary name does not prove ownership.
"""

import os
import stat
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OperationStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.owner_pidfd import close_owned
from .filesystem import FileEvidenceStore
from .inspection_result import (
    StorageFileIdentity,
    StorageObservation,
    StorageInspectionFailure,
)
from .temporary_identity import exchange_temporary_name
from lab_generate_skill.domain.evidence_io import EvidenceCommand


def _identity(info: os.stat_result) -> StorageFileIdentity:
    return StorageFileIdentity(info.st_dev, info.st_ino, info.st_mode, info.st_size)


def _same_directory(before: StorageFileIdentity, after: os.stat_result) -> bool:
    return (before.device, before.inode, stat.S_IFMT(before.mode)) == (
        after.st_dev,
        after.st_ino,
        stat.S_IFMT(after.st_mode),
    ) and stat.S_ISDIR(after.st_mode)


def inspect_exchange_storage(
    command: EvidenceCommand, control: OperationControl
) -> StorageObservation:
    command = EvidenceCommand.model_validate(command)
    control.checkpoint()
    temporary = (
        exchange_temporary_name(command.exchange_id)
        if command.operation == "put"
        else None
    )
    observation = StorageObservation(
        command,
        datetime.now(timezone.utc),
        None,
        None,
        "unknown",
        temporary,
        "unknown" if temporary else "not_applicable",
        None,
    )
    phase = "root"
    fds: list[int] = []
    primary: BaseException | None = None
    try:
        try:
            root = Path(command.root)
            if root.resolve(strict=True) != root:
                raise EvidenceIntegrityError("Storage inspection rejects root aliases")
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            fds.append(root_fd)
            observation = replace(observation, root=_identity(os.fstat(root_fd)))
            control.checkpoint()
            phase = "blobs"
            try:
                directory = os.open(
                    "blobs",
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=root_fd,
                )
            except FileNotFoundError:
                directory = None
                observation = replace(
                    observation,
                    object_state="absent",
                    temporary_state="absent" if temporary else "not_applicable",
                )
            if directory is not None:
                fds.append(directory)
                observation = replace(observation, blobs=_identity(os.fstat(directory)))
                # Constructor performs no initialization; all object bytes below
                # come from the pinned descriptor, not a second pathname lookup.
                store = FileEvidenceStore(
                    root, max_object_bytes=command.max_object_bytes, initialize=False
                )
                errors: list[Exception] = []
                phase = "object"
                control.checkpoint()
                try:
                    store._read_verified(directory, command.reference)
                    observation = replace(observation, object_state="present")
                except EvidenceNotFound:
                    observation = replace(observation, object_state="absent")
                except Exception as error:
                    errors.append(error)
                try:
                    control.checkpoint()
                except BaseException as stopped:
                    if errors:
                        raise BaseExceptionGroup(
                            "Storage check and stop failed", [*errors, stopped]
                        ) from None
                    raise
                phase = "temporary"
                if temporary is not None:
                    try:
                        info = os.stat(
                            temporary, dir_fd=directory, follow_symlinks=False
                        )
                        observation = replace(
                            observation,
                            temporary=_identity(info),
                            temporary_state=(
                                "present" if stat.S_ISREG(info.st_mode) else "unsafe"
                            ),
                        )
                    except FileNotFoundError:
                        observation = replace(observation, temporary_state="absent")
                    except Exception as error:
                        errors.append(error)
                if errors:
                    phase = "checks"
                    raise ExceptionGroup(
                        "Original storage object/temporary checks failed", errors
                    )
            phase = "recheck"
            control.checkpoint()
            assert observation.root is not None
            if not _same_directory(
                observation.root, os.stat(root, follow_symlinks=False)
            ):
                raise EvidenceIntegrityError(
                    "Original storage root changed during inspection"
                )
            if observation.blobs is not None:
                if not _same_directory(
                    observation.blobs,
                    os.stat("blobs", dir_fd=root_fd, follow_symlinks=False),
                ):
                    raise EvidenceIntegrityError(
                        "Original blobs directory changed during inspection"
                    )
            else:
                try:
                    os.stat("blobs", dir_fd=root_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise EvidenceIntegrityError(
                        "Blobs directory appeared during inspection"
                    )
            control.checkpoint()
        except BaseException as error:
            primary = error
            raise
        finally:
            # Independent fd cleanup is attempted even after control stops.
            # Outer supervision owns the hard bound if close itself blocks.
            if primary is None:
                phase = "close"
            close_owned(fds, primary)
        phase = "completion"
        control.checkpoint()
        return replace(observation, observed_at=datetime.now(timezone.utc))
    except BaseException as error:
        if isinstance(error, OperationStopped) or not isinstance(error, Exception):
            setattr(error, "storage_inspection", observation)
            raise
        raise StorageInspectionFailure(phase, observation) from error
