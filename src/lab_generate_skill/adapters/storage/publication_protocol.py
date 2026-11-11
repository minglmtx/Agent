"""Bounded fixed-entry publication read wire; no mutation or dynamic dispatch."""

import hashlib
from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.storage_scope import (
    StorageScope,
    check_storage_scope_operation,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.release_activation import ReleaseDeployment
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from lab_generate_skill.adapters.processes.wire_json import json_object
from .installation_receipt import check_storage_installation

ENTRY = "lab_generate_skill.bootstrap.storage_publication"
MAX_REQUEST = 13 * 1024 * 1024
MAX_REPLY = 13 * 1024 * 1024


def check_publication_root(root: str, scope: StorageScope) -> None:
    path, workspace = PurePosixPath(root), PurePosixPath(scope.workspace_root)
    if (
        not path.is_absolute()
        or str(path) != root
        or ".." in path.parts
        or "\0" in root
        or "\\" in root
        or path == workspace
        or not path.is_relative_to(workspace)
    ):
        raise ValueError("Publication root must be a canonical workspace subdirectory")
    for value in (scope.config.evidence_root, scope.config.session_root):
        other = PurePosixPath(value)
        if path.is_relative_to(other) or other.is_relative_to(path):
            raise ValueError("Publication and storage directories must be disjoint")


class PublicationReadCommand(Contract):
    schema_version: Literal["publication-read-command/1"] = "publication-read-command/1"
    scope: StorageScope
    deployment: ReleaseDeployment
    root: str = Field(min_length=1, max_length=4096)
    operation: OperationContext

    @model_validator(mode="after")
    def binding(self) -> Self:
        check_publication_root(self.root, self.scope)
        check_storage_scope_operation(self.scope, self.operation)
        return self


PublicationPhase = Literal[
    "parent_guard", "installation", "membership", "read", "verification", "completion"
]


class PublicationReadReply(Contract):
    schema_version: Literal["publication-read-reply/1"] = "publication-read-reply/1"
    command_sha256: Sha256
    worker: ProcessIdentity
    phase: PublicationPhase
    error: RemoteError | None
    installed_sources: InstalledReleaseSources | None
    membership: SlurmCgroupMembership | None
    snapshot: ReleaseCurrentSnapshot | None

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.error is not None:
            validate_error_budget(self.error)
        elif (
            self.phase != "completion"
            or self.installed_sources is None
            or self.membership is None
            or self.snapshot is None
        ):
            raise ValueError(
                "Publication success requires complete original observations"
            )
        return self


def encode_publication_command(command: PublicationReadCommand) -> bytes:
    raw = PublicationReadCommand.model_validate(command).model_dump_json().encode()
    if len(raw) > MAX_REQUEST:
        raise ValueError("Publication command exceeds bound")
    return raw


def decode_publication_command(raw: bytes) -> PublicationReadCommand:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REQUEST:
        raise ValueError("Invalid bounded publication command")
    json_object(raw)
    return PublicationReadCommand.model_validate_json(raw)


def encode_publication_reply(reply: PublicationReadReply) -> bytes:
    raw = PublicationReadReply.model_validate(reply).model_dump_json().encode()
    if len(raw) > MAX_REPLY:
        raise ValueError("Publication reply exceeds bound")
    return raw


def decode_publication_reply(command: bytes, raw: bytes) -> PublicationReadReply:
    original = decode_publication_command(command)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REPLY:
        raise ValueError("Invalid bounded publication reply")
    json_object(raw)
    reply = PublicationReadReply.model_validate_json(raw)
    if reply.command_sha256 != hashlib.sha256(command).hexdigest():
        raise ValueError("Publication reply belongs to another command")
    controller = original.scope.writer
    if (reply.worker.node_id, reply.worker.boot_id) != (
        controller.node_id,
        controller.boot_id,
    ) or reply.worker.process_id == controller.process_id:
        raise ValueError("Publication worker differs from local delegated child")
    check_storage_installation(
        original.scope.config,
        reply.installed_sources,
        entry_module=ENTRY,
        required=reply.error is None,
    )
    if reply.membership is not None and (
        reply.membership.writer != reply.worker
        or reply.membership.job_id != original.scope.execution.raw_job_id
        or reply.membership.uid != original.scope.execution.uid
    ):
        raise ValueError("Publication membership differs from original execution")
    if reply.snapshot is not None and reply.snapshot.deployment != original.deployment:
        raise ValueError("Publication snapshot belongs to another deployment")
    return reply
