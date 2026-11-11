"""Independent linked-cleanup wire; carries original command, never repeats it."""

import hashlib
from dataclasses import dataclass
from typing import Literal, Self
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from lab_generate_skill.domain.storage_unregistered import StorageUnregisteredExchange
from lab_generate_skill.domain.validation import Contract, Sha256
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionResolution,
    EvidenceWorkerInstance,
    check_evidence_cleanup,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from lab_generate_skill.adapters.processes.wire_json import json_object
from .registered_protocol import (
    RegisteredStorageCommand,
    _head,
    _split,
    MAX_SNAPSHOT_BYTES,
    encode_registered_command,
)
from .worker_protocol import encode_command
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from .installation_receipt import check_storage_installation


class StorageResolutionCommand(Contract):
    schema_version: Literal["storage-resolution-command/3"] = (
        "storage-resolution-command/3"
    )
    original: RegisteredStorageCommand
    cleanup: OperationContext
    ending: StorageProcessEnd | None

    @model_validator(mode="after")
    def original_scope(self) -> Self:
        if self.original.action != "exchange":
            raise ValueError("Only an original physical exchange can be resolved")
        check_evidence_cleanup(self.original.operation, self.cleanup)
        if self.cleanup.cancellation_ref is not None:
            raise ValueError("Storage cleanup needs independent bounded control")
        if (
            self.ending is not None
            and self.ending.controller != self.original.controller
        ):
            raise ValueError("Original reap belongs to another controller")
        return self


class StorageResolutionReply(Contract):
    schema_version: Literal[
        "storage-resolution-reply/3", "storage-resolution-reply/4"
    ] = "storage-resolution-reply/3"
    request_sha256: Sha256
    worker: EvidenceWorkerInstance
    phase: str = Field(min_length=1, max_length=64)
    installed_sources: InstalledReleaseSources | None = None
    error: RemoteError | None = None
    resolution: EvidenceSessionResolution | None = None
    not_registered: StorageUnregisteredExchange | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        value: dict[str, object] = handler(self)
        if self.schema_version == "storage-resolution-reply/3":
            value.pop("not_registered", None)
        return value

    @model_validator(mode="after")
    def version(self) -> Self:
        if self.schema_version == "storage-resolution-reply/4":
            if (
                self.not_registered is None
                or self.resolution is not None
                or self.error is not None
                or self.phase != "completion"
            ):
                raise ValueError(
                    "Version4 requires only a complete unregistered-exchange proof"
                )
        elif self.not_registered is not None:
            raise ValueError("Unregistered-exchange proof requires reply version4")
        return self

    @model_validator(mode="after")
    def error_budget(self) -> Self:
        if self.error is not None:
            validate_error_budget(self.error)
        return self


@dataclass(frozen=True)
class StorageResolutionResult:
    reply: StorageResolutionReply
    snapshot: EvidenceSessionSnapshot | None


def encode_resolution_command(
    command: StorageResolutionCommand, payload: bytes
) -> bytes:
    command = StorageResolutionCommand.model_validate(command)
    original = encode_registered_command(command.original, payload)
    if (
        command.ending is not None
        and command.ending.request_sha256 != hashlib.sha256(original).hexdigest()
    ):
        raise ValueError("Ending is not bound to original full request")
    return _head(command) + payload


def decode_resolution_command(raw: bytes) -> tuple[StorageResolutionCommand, bytes]:
    head, body = _split(raw)
    command = StorageResolutionCommand.model_validate_json(head)
    encode_resolution_command(command, body)
    return command, body


def encode_resolution_reply(
    reply: StorageResolutionReply, snapshot: EvidenceSessionSnapshot | None
) -> bytes:
    reply = StorageResolutionReply.model_validate(reply)
    raw = (
        b""
        if snapshot is None
        else EvidenceSessionSnapshot.model_validate(snapshot).model_dump_json().encode()
    )
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Resolver snapshot exceeds budget")
    return _head(reply) + raw


def decode_resolution_reply(request: bytes, raw: bytes) -> StorageResolutionResult:
    command, payload = decode_resolution_command(request)
    header, body = _split(raw)
    reply = StorageResolutionReply.model_validate_json(header)
    if reply.request_sha256 != hashlib.sha256(request).hexdigest():
        raise ValueError("Resolution reply differs from original request")
    original = command.original
    check_storage_installation(
        original.config,
        reply.installed_sources,
        entry_module="lab_generate_skill.bootstrap.evidence_resolver",
        required=reply.error is None,
    )
    assert original.io is not None
    result = reply.resolution
    absent = reply.not_registered
    if result is not None:
        if (
            result.operation != command.cleanup
            or result.exchange_id != original.io.exchange_id
            or result.resolution_id
            != "resolve-"
            + hashlib.sha256(command.cleanup.operation_id.encode()).hexdigest()
        ):
            raise ValueError("Resolution differs from original cleanup")
        if result.worker_end is not None:
            ending = command.ending
            if (
                ending is None
                or result.worker_end.worker.process_id != ending.process_id
                or result.worker_end.returncode != ending.returncode
                or result.worker_end.observed_at != ending.observed_at
                or result.worker_end.proof_sha256 != ending.sha256
                or result.worker_end.verifier_id != "original-storage-controller"
            ):
                raise ValueError("Resolution differs from original observed reap")
    snapshot = None
    if body:
        if len(body) > MAX_SNAPSHOT_BYTES:
            raise ValueError("Resolver snapshot exceeds budget")
        json_object(body)
        snapshot = EvidenceSessionSnapshot.model_validate_json(body)
        if (
            snapshot.binding != original.binding
            or snapshot.capacity != original.config.capacity
        ):
            raise ValueError("Resolver snapshot belongs to another scope")
        entry = next(
            (
                e
                for e in snapshot.entries
                if e.intent.exchange_id == original.io.exchange_id
            ),
            None,
        )
        if absent is not None:
            if (
                command.ending is None
                or original.expected_revision is None
                or body != snapshot.model_dump_json().encode()
            ):
                raise ValueError(
                    "Original ending and canonical unchanged history required"
                )
            absent.check(
                snapshot,
                exchange_id=original.io.exchange_id,
                request_sha256=hashlib.sha256(
                    encode_registered_command(original, payload)
                ).hexdigest(),
                binding=original.binding,
                operation=command.cleanup,
                ending=command.ending,
                observer=reply.worker,
                expected_revision=original.expected_revision,
            )
        elif (
            entry is None
            or result is None
            or result not in entry.resolutions
            or entry.intent.operation != original.operation
            or entry.intent.command_sha256
            != hashlib.sha256(encode_command(original.io, payload)).hexdigest()
        ):
            raise ValueError("Resolution is not in original confirmed history")
    if reply.error is None:
        if (
            reply.phase != "completion"
            or (result is None and absent is None)
            or snapshot is None
        ):
            raise ValueError("Resolver success lacks original confirmed resolution")
    elif snapshot is not None:
        raise ValueError("Failed resolver cannot claim snapshot acknowledgement")
    return StorageResolutionResult(reply, snapshot)
