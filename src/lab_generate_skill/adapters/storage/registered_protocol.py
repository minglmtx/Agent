"""Fixed registered worker framing; bounded JSON metadata and original bytes.

No dynamic entrypoints, callbacks, environment, pickle, retry or recovery commands.
A reply carries a snapshot only when its acknowledgement was actually returned.
"""

import hashlib
import struct
from typing import Literal, Self
from dataclasses import dataclass
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceWorkerInstance,
    EvidenceOperationIntent,
    EvidenceOperationOutcome,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from .installation_receipt import check_storage_installation
from .physical_exchange import outcome_from_reply
from lab_generate_skill.domain.evidence_io import EvidenceCommand
from .worker_protocol import MAX_PACKET_BYTES, encode_command, decode_reply

MAX_REGISTERED_HEADER_BYTES = 13 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_REGISTERED_PACKET = (
    8 + MAX_REGISTERED_HEADER_BYTES + MAX_SNAPSHOT_BYTES + MAX_PACKET_BYTES
)


class RegisteredStorageCommand(Contract):
    schema_version: Literal[
        "registered-storage-command/3", "registered-storage-command/4"
    ] = "registered-storage-command/3"
    action: Literal["create", "exchange", "open_existing"]
    binding: EvidenceSessionBinding
    config: EvidenceStorageConfig
    operation: OperationContext
    controller: ProcessIdentity
    expected_revision: int | None = Field(default=None, ge=0)
    io: EvidenceCommand | None = None

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        if (self.schema_version == "registered-storage-command/4") != (
            self.action == "open_existing"
        ):
            raise ValueError("Existing-only namespace open requires explicit command/4")
        if (self.binding.storage_id, self.binding.storage_config_sha256) != (
            self.config.storage_id,
            self.config.sha256,
        ):
            raise ValueError("Storage binding differs from frozen configuration")
        if self.binding.release_id != self.config.installation.manifest.release_id:
            raise ValueError("Storage scope differs from installation release")
        op = self.operation
        if (op.run_id, op.owner_id) != (
            self.binding.owner.run_id,
            self.binding.owner.owner_id,
        ):
            raise ValueError("Storage operation belongs to another owner")
        if (
            op.mode != "execute"
            or op.parent_operation_id is not None
            or op.cancellation_ref is not None
            or op.attempt_id is not None
            or op.allocation_id is not None
            or op.recovery_ref is not None
        ):
            raise ValueError("Worker requires a private physical execute operation")
        if self.action in ("create", "open_existing"):
            if self.io is not None or self.expected_revision is not None:
                raise ValueError("Create cannot perform a physical exchange")
        elif self.io is None or self.expected_revision is None:
            raise ValueError("Exchange needs command and exact original revision")
        elif (self.io.root, self.io.max_object_bytes) != (
            self.config.evidence_root,
            self.config.max_object_bytes,
        ):
            raise ValueError("Physical command differs from frozen root or limit")
        return self


class RegisteredStorageReply(Contract):
    schema_version: Literal[
        "registered-storage-reply/3", "registered-storage-reply/4"
    ] = "registered-storage-reply/3"
    command_sha256: Sha256
    worker: EvidenceWorkerInstance
    phase: str = Field(min_length=1, max_length=64)
    installed_sources: InstalledReleaseSources | None = None
    error: RemoteError | None = None
    intent: EvidenceOperationIntent | None = None
    outcome: EvidenceOperationOutcome | None = None

    @model_validator(mode="after")
    def bounded_error(self) -> Self:
        if self.error is not None:
            validate_error_budget(self.error)
        if self.outcome is not None and self.intent is None:
            raise ValueError("Outcome without original intent")
        if self.intent is not None and self.intent.worker != self.worker:
            raise ValueError("Reply and intent workers differ")
        return self


@dataclass(frozen=True)
class RegisteredWorkerResult:
    reply: RegisteredStorageReply
    snapshot: EvidenceSessionSnapshot | None
    raw_reply: bytes


def _head(header: Contract) -> bytes:
    raw = header.model_dump_json().encode()
    if len(raw) > MAX_REGISTERED_HEADER_BYTES:
        raise ValueError("Registered worker header exceeds budget")
    return struct.pack(">I", len(raw)) + raw


def _split(raw: bytes) -> tuple[bytes, bytes]:
    if type(raw) is not bytes or not 4 <= len(raw) <= MAX_REGISTERED_PACKET:
        raise ValueError("Registered worker packet outside bounds")
    n = struct.unpack(">I", raw[:4])[0]
    if not 1 <= n <= MAX_REGISTERED_HEADER_BYTES or len(raw) < 4 + n:
        raise ValueError("Truncated or oversized registered header")
    header = raw[4 : 4 + n]
    json_object(header)
    return header, raw[4 + n :]


def encode_registered_command(
    command: RegisteredStorageCommand, payload: bytes = b""
) -> bytes:
    command = RegisteredStorageCommand.model_validate(command)
    if type(payload) is not bytes:
        raise TypeError("Payload must be exact bytes")
    if command.io is None:
        if payload:
            raise ValueError("Create has no payload")
    else:
        encode_command(command.io, payload)
    return _head(command) + payload


def decode_registered_command(raw: bytes) -> tuple[RegisteredStorageCommand, bytes]:
    header, payload = _split(raw)
    command = RegisteredStorageCommand.model_validate_json(header)
    encode_registered_command(command, payload)
    return command, payload


def encode_registered_reply(
    reply: RegisteredStorageReply,
    snapshot: EvidenceSessionSnapshot | None,
    raw_reply: bytes = b"",
) -> bytes:
    reply = RegisteredStorageReply.model_validate(reply)
    data = (
        b""
        if snapshot is None
        else EvidenceSessionSnapshot.model_validate(snapshot).model_dump_json().encode()
    )
    if (
        type(raw_reply) is not bytes
        or len(raw_reply) > MAX_PACKET_BYTES
        or len(data) > MAX_SNAPSHOT_BYTES
    ):
        raise ValueError("Registered reply payload exceeds bounds")
    return _head(reply) + struct.pack(">I", len(data)) + data + raw_reply


def decode_registered_reply(request: bytes, raw: bytes) -> RegisteredWorkerResult:
    command, payload = decode_registered_command(request)
    header, body = _split(raw)
    reply = RegisteredStorageReply.model_validate_json(header)
    expected_version = (
        "registered-storage-reply/4"
        if command.action == "open_existing"
        else "registered-storage-reply/3"
    )
    if reply.schema_version != expected_version:
        raise ValueError("Registered reply changed original command version")
    if reply.command_sha256 != hashlib.sha256(request).hexdigest() or len(body) < 4:
        raise ValueError("Reply does not bind original request")
    n = struct.unpack(">I", body[:4])[0]
    if n > MAX_SNAPSHOT_BYTES or len(body) < 4 + n:
        raise ValueError("Invalid snapshot frame")
    snapshot = None
    if n:
        data = body[4 : 4 + n]
        json_object(data)
        snapshot = EvidenceSessionSnapshot.model_validate_json(data)
        if (
            snapshot.binding != command.binding
            or snapshot.capacity != command.config.capacity
        ):
            raise ValueError("Snapshot differs from original storage scope")
    check_storage_installation(
        command.config,
        reply.installed_sources,
        entry_module="lab_generate_skill.bootstrap.evidence_worker",
        required=reply.error is None,
    )
    physical = body[4 + n :]
    if len(physical) > MAX_PACKET_BYTES:
        raise ValueError("Physical reply exceeds budget")
    if command.action in ("create", "open_existing"):
        if physical or reply.intent is not None or reply.outcome is not None:
            raise ValueError("Create cannot report an exchange")
    else:
        assert command.io is not None
        if reply.intent is not None:
            intent = reply.intent
            if (
                intent.operation != command.operation
                or intent.controller != command.controller
                or intent.command != command.io
                or intent.exchange_id != command.io.exchange_id
                or intent.kind != command.io.operation
                or intent.reference != command.io.reference
                or intent.command_sha256
                != hashlib.sha256(encode_command(command.io, payload)).hexdigest()
            ):
                raise ValueError("Reply intent differs from original physical command")
        if physical:
            parsed, _ = decode_reply(command.io, physical)
            if reply.outcome is not None:
                expected = outcome_from_reply(command.io, physical, command.operation)
                if reply.outcome != expected:
                    raise ValueError("Outcome differs from original reply bytes")
        elif reply.outcome is not None:
            raise ValueError("Outcome without actual reply")
    if reply.error is None:
        if reply.phase != "completion" or snapshot is None:
            raise ValueError("Successful worker reply lacks confirmed snapshot")
        if command.action == "exchange":
            assert command.expected_revision is not None
            if (
                reply.intent is None
                or reply.outcome is None
                or not physical
                or snapshot.revision != command.expected_revision + 2
                or not snapshot.entries
                or snapshot.entries[-1].intent != reply.intent
                or snapshot.entries[-1].outcome != reply.outcome
                or snapshot.entries[-1].resolutions
            ):
                raise ValueError("Exchange acknowledgement is not exact")
    elif snapshot is not None:
        raise ValueError("Failed worker cannot claim a confirmed snapshot")
    return RegisteredWorkerResult(reply, snapshot, physical)
