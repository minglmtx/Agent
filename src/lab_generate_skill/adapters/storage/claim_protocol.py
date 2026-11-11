"""Bounded fixed-entry claim read wire; no mutation or dynamic dispatch."""

import hashlib
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from pydantic import Field, TypeAdapter, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.storage_scope import (
    StorageScope,
    check_storage_scope_operation,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.claims import SourceClaimRecord
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from lab_generate_skill.adapters.processes.wire_json import json_object
from .installation_receipt import check_storage_installation

ENTRY = "lab_generate_skill.bootstrap.storage_claim"
MAX_REQUEST = 13 * 1024 * 1024
MAX_REPLY = 13 * 1024 * 1024


def check_claim_root(root: str, scope: StorageScope) -> None:
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
        raise ValueError("Claim root must be a canonical workspace subdirectory")
    for value in (scope.config.evidence_root, scope.config.session_root):
        other = PurePosixPath(value)
        if path.is_relative_to(other) or other.is_relative_to(path):
            raise ValueError("Claim and storage directories must be disjoint")


class ClaimReadCommand(Contract):
    schema_version: Literal["claim-read-command/1"] = "claim-read-command/1"
    scope: StorageScope
    root: str = Field(min_length=1, max_length=4096)
    operation: OperationContext

    @model_validator(mode="after")
    def binding(self) -> Self:
        if self.scope.claim is None:
            raise ValueError("Claim read requires a complete source scope")
        check_claim_root(self.root, self.scope)
        check_storage_scope_operation(self.scope, self.operation)
        return self


class StageValidationClaimReadCommand(Contract):
    schema_version: Literal["claim-read-command/2"] = "claim-read-command/2"
    scope: StorageScope
    root: str = Field(min_length=1, max_length=4096)
    operation: OperationContext
    validation: SourceStageValidation

    @model_validator(mode="after")
    def binding(self) -> Self:
        if self.scope.claim is None:
            raise ValueError("Stage-validation read requires complete current scope")
        check_claim_root(self.root, self.scope)
        check_storage_scope_operation(self.scope, self.operation)
        self.validation.require_current_binding(self.scope.claim)
        return self


ClaimReadRequest = Annotated[
    ClaimReadCommand | StageValidationClaimReadCommand,
    Field(discriminator="schema_version"),
]
CLAIM_READ_REQUEST: TypeAdapter[ClaimReadRequest] = TypeAdapter(ClaimReadRequest)


ClaimPhase = Literal[
    "parent_guard", "installation", "membership", "read", "verification", "completion"
]


class ClaimReadReply(Contract):
    schema_version: Literal["claim-read-reply/1"] = "claim-read-reply/1"
    command_sha256: Sha256
    worker: ProcessIdentity
    phase: ClaimPhase
    error: RemoteError | None
    installed_sources: InstalledReleaseSources | None
    membership: SlurmCgroupMembership | None
    record: SourceClaimRecord | None

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.error is not None:
            validate_error_budget(self.error)
        elif (
            self.phase != "completion"
            or self.installed_sources is None
            or self.membership is None
            or self.record is None
        ):
            raise ValueError("Claim success requires complete original observations")
        return self


def encode_claim_command(command: ClaimReadRequest) -> bytes:
    raw = CLAIM_READ_REQUEST.validate_python(command).model_dump_json().encode()
    if len(raw) > MAX_REQUEST:
        raise ValueError("Claim command exceeds bound")
    return raw


def decode_claim_command(raw: bytes) -> ClaimReadRequest:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REQUEST:
        raise ValueError("Invalid bounded claim command")
    json_object(raw)
    return CLAIM_READ_REQUEST.validate_json(raw)


def encode_claim_reply(reply: ClaimReadReply) -> bytes:
    raw = ClaimReadReply.model_validate(reply).model_dump_json().encode()
    if len(raw) > MAX_REPLY:
        raise ValueError("Claim reply exceeds bound")
    return raw


def decode_claim_reply(command: bytes, raw: bytes) -> ClaimReadReply:
    original = decode_claim_command(command)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REPLY:
        raise ValueError("Invalid bounded claim reply")
    json_object(raw)
    reply = ClaimReadReply.model_validate_json(raw)
    if reply.command_sha256 != hashlib.sha256(command).hexdigest():
        raise ValueError("Claim reply belongs to another command")
    controller = original.scope.writer
    if (reply.worker.node_id, reply.worker.boot_id) != (
        controller.node_id,
        controller.boot_id,
    ) or reply.worker.process_id == controller.process_id:
        raise ValueError("Claim worker differs from local delegated child")
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
        raise ValueError("Claim membership differs from original execution")
    if reply.record is not None and reply.record.binding != original.scope.claim:
        raise ValueError("Claim record differs from complete original source binding")
    return reply
