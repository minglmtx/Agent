"""Evidence worker/1 framing and validation; all helpers are filesystem-free.

One 4-byte big-endian header length, strict UTF-8 JSON header, then raw bytes.
There is exactly one request/reply per process. No pickle, callback or shell.
References are precomputed expectations, never proof that writes committed.
"""

import hashlib
import struct
from typing import Literal, Self
from pydantic import model_validator

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_io import EvidenceCommand, MAX_OBJECT_BYTES
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.validation import Contract, Identifier
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    validate_error_budget,
)
from lab_generate_skill.adapters.processes.wire_json import json_object

MAX_HEADER_BYTES = 64 * 1024
MAX_PACKET_BYTES = 4 + MAX_HEADER_BYTES + MAX_OBJECT_BYTES


class EvidenceReply(Contract):
    schema_version: Literal["evidence-io-reply/1"] = "evidence-io-reply/1"
    exchange_id: Identifier
    operation: Literal["read", "put"]
    reference: EvidenceRef
    error: RemoteError | None = None

    @model_validator(mode="after")
    def check_error(self) -> Self:
        if self.error is not None:
            validate_error_budget(self.error)
        return self


def _frame(header: Contract, payload: bytes) -> bytes:
    raw = header.model_dump_json().encode("utf-8")
    if len(raw) > MAX_HEADER_BYTES or len(payload) > MAX_OBJECT_BYTES:
        raise ValueError("Worker packet exceeds framing budget")
    return struct.pack(">I", len(raw)) + raw + payload


def _unframe(raw: bytes) -> tuple[bytes, bytes]:
    if type(raw) is not bytes:
        raise TypeError("Worker packet must be exact bytes")
    if not 4 <= len(raw) <= MAX_PACKET_BYTES:
        raise ValueError("Worker packet size outside bounds")
    size = struct.unpack(">I", raw[:4])[0]
    if not 1 <= size <= MAX_HEADER_BYTES or 4 + size > len(raw):
        raise ValueError("Invalid or truncated worker header")
    header, payload = raw[4 : 4 + size], raw[4 + size :]
    json_object(header)  # reject duplicate/nonfinite JSON before typed decoding
    return header, payload


def _check_bytes(data: bytes, reference: EvidenceRef) -> None:
    if (
        len(data) != reference.size_bytes
        or hashlib.sha256(data).hexdigest() != reference.sha256
    ):
        raise ValueError("Worker bytes do not match expected reference")


def _check_request_payload(command: EvidenceCommand, payload: bytes) -> None:
    if type(payload) is not bytes:
        raise TypeError("Worker payload must be exact bytes")
    if command.operation == "read":
        if payload:
            raise ValueError("Read request cannot contain payload")
    else:
        assert command.metadata is not None
        if evidence_reference(payload, command.metadata) != command.reference:
            raise ValueError("Put payload/metadata differs from expected reference")


def encode_command(command: EvidenceCommand, payload: bytes = b"") -> bytes:
    command = EvidenceCommand.model_validate(command)
    _check_request_payload(command, payload)
    return _frame(command, payload)


def decode_command(raw: bytes) -> tuple[EvidenceCommand, bytes]:
    header, payload = _unframe(raw)
    command = EvidenceCommand.model_validate_json(header)
    _check_request_payload(command, payload)
    return command, payload


def _check_reply(
    command: EvidenceCommand, reply: EvidenceReply, payload: bytes
) -> None:
    if (reply.exchange_id, reply.operation, reply.reference) != (
        command.exchange_id,
        command.operation,
        command.reference,
    ):
        raise ValueError("Worker reply belongs to a different exchange or reference")
    if type(payload) is not bytes:
        raise TypeError("Worker payload must be exact bytes")
    if reply.error is not None or reply.operation == "put":
        if payload:
            raise ValueError("Failure/write reply cannot expose payload")
    else:
        _check_bytes(payload, command.reference)


def encode_reply(
    command: EvidenceCommand, reply: EvidenceReply, payload: bytes = b""
) -> bytes:
    command = EvidenceCommand.model_validate(command)
    reply = EvidenceReply.model_validate(reply)
    _check_reply(command, reply, payload)
    return _frame(reply, payload)


def decode_reply(command: EvidenceCommand, raw: bytes) -> tuple[EvidenceReply, bytes]:
    command = EvidenceCommand.model_validate(command)
    header, payload = _unframe(raw)
    reply = EvidenceReply.model_validate_json(header)
    _check_reply(command, reply, payload)
    return reply, payload
