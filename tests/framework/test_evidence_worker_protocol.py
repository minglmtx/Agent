"""Framing, identity, limits and hostile messages cannot become valid evidence."""

import json
import struct
from pathlib import Path
from typing import cast
import pytest

from lab_generate_skill.domain.evidence_io import EvidenceCommand
from lab_generate_skill.adapters.storage.worker_protocol import (
    EvidenceReply,
    MAX_HEADER_BYTES,
    decode_command,
    decode_reply,
    encode_command,
    encode_reply,
)
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    describe_error,
    validate_error_budget,
)
from evidence_worker_fixtures import command


def frame(header: bytes, body: bytes = b"") -> bytes:
    return struct.pack(">I", len(header)) + header + body


@pytest.mark.parametrize("data", [b"", b"\x00\xff\xfe", b"x" * 65536])
def test_exact_command_and_read_reply_roundtrip(tmp_path: Path, data: bytes) -> None:
    put = command(tmp_path, data)
    assert decode_command(encode_command(put, data)) == (put, data)
    read = command(tmp_path, data, "read")
    assert decode_command(encode_command(read)) == (read, b"")
    reply = EvidenceReply(
        exchange_id=read.exchange_id, operation="read", reference=read.reference
    )
    assert decode_reply(read, encode_reply(read, reply, data)) == (reply, data)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\0",
        b"\0" * 4,
        b"\0\0\x00\x10{}",
        frame(b"[]"),
        frame(b"null"),
        frame(b"\xff"),
        frame(b"{}{}"),
        frame(b'{"x":1,"x":2}'),
        frame(b'{"x":NaN}'),
        struct.pack(">I", MAX_HEADER_BYTES + 1),
    ],
)
def test_malformed_frames_rejected(raw: bytes) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        decode_command(raw)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "evidence-io-command/0"},
        {"operation": "execute"},
        {"root": "relative"},
        {"root": "/safe/../outside"},
        {"root": "/safe\0"},
        {"max_object_bytes": 0},
        {"max_object_bytes": True},
        {"max_object_bytes": "9"},
        {"metadata": None},
        {"exchange_id": ""},
        {"callback": "os.system"},
    ],
)
def test_invalid_command_rejected(tmp_path: Path, change: dict[str, object]) -> None:
    fields = command(tmp_path).model_dump(mode="json")
    fields.update(change)
    with pytest.raises(ValueError):
        decode_command(frame(json.dumps(fields).encode(), b"evidence"))


@pytest.mark.parametrize("data", [b"", b"evidencf", b"evidence!", b" evidence"])
def test_put_digest_size_or_trailing_bytes_rejected(
    tmp_path: Path, data: bytes
) -> None:
    original = command(tmp_path)
    with pytest.raises(ValueError):
        decode_command(frame(original.model_dump_json().encode(), data))


def test_metadata_and_read_payload_cannot_be_smuggled(tmp_path: Path) -> None:
    put = command(tmp_path)
    other = (
        put.model_copy(
            update={"metadata": put.metadata.model_copy(update={"producer": "other"})}
        )
        if put.metadata
        else put
    )
    with pytest.raises(ValueError):
        encode_command(other, b"evidence")
    read = command(tmp_path, operation="read")
    with pytest.raises(ValueError):
        encode_command(read, b"evidence")
    with pytest.raises(ValueError):
        encode_command(read.model_copy(update={"metadata": put.metadata}))


@pytest.mark.parametrize(
    "change",
    [
        {"exchange_id": "other"},
        {"operation": "read"},
        {"schema_version": "evidence-io-reply/0"},
    ],
)
def test_reply_must_match_exchange(tmp_path: Path, change: dict[str, object]) -> None:
    request = command(tmp_path)
    fields = EvidenceReply(
        exchange_id=request.exchange_id, operation="put", reference=request.reference
    ).model_dump(mode="json")
    fields.update(change)
    with pytest.raises(ValueError):
        decode_reply(request, frame(json.dumps(fields).encode()))


def test_wrong_ref_read_bytes_and_failure_payload_are_rejected(tmp_path: Path) -> None:
    request = command(tmp_path, operation="read")
    reply = EvidenceReply(
        exchange_id=request.exchange_id, operation="read", reference=request.reference
    )
    with pytest.raises(ValueError):
        decode_reply(request, frame(reply.model_dump_json().encode(), b"evidencf"))
    wrong = reply.model_copy(
        update={"reference": command(tmp_path, b"different").reference}
    )
    with pytest.raises(ValueError):
        encode_reply(request, wrong, b"different")
    failure = reply.model_copy(update={"error": RemoteError(type_name="OSError")})
    with pytest.raises(ValueError):
        encode_reply(request, failure, b"secret")
    assert decode_reply(request, encode_reply(request, failure)) == (failure, b"")


@pytest.mark.parametrize("raw", [None, "text", bytearray(b"test"), {}, 1])
def test_packet_type_is_exact_bytes(raw: object) -> None:
    with pytest.raises(TypeError):
        decode_command(cast(bytes, raw))


def test_remote_error_keeps_order_cause_errno_and_safe_frames() -> None:
    secret = "private-evidence-not-for-diagnostics"
    try:
        try:
            raise OSError(5, secret)
        except OSError as original:
            raise RuntimeError(secret) from original
    except RuntimeError as primary:
        group = ExceptionGroup(secret, [primary, PermissionError(13, secret)])
    fact = describe_error(group)
    validate_error_budget(fact)
    assert [e.type_name for e in fact.children] == ["RuntimeError", "PermissionError"]
    cause = fact.children[0].cause
    assert cause is not None and cause.type_name == "OSError" and cause.errno == 5
    assert cause.frames and fact.children[0].context_suppressed
    assert fact.children[1].errno == 13 and not fact.truncated
    assert secret not in fact.model_dump_json()


def test_remote_error_cycles_and_wide_groups_have_explicit_limits() -> None:
    cyclic = ValueError("loop")
    cyclic.__cause__ = cyclic
    fact = describe_error(cyclic)
    assert fact.cause is not None and fact.cause.truncated
    validate_error_budget(fact)
    wide = describe_error(ExceptionGroup("many", [OSError("x") for _ in range(40)]))
    assert wide.truncated and len(wide.children) == 15
    validate_error_budget(wide)
    excessive = RemoteError(
        type_name="group",
        children=tuple(RemoteError(type_name="leaf") for _ in range(16)),
    )
    with pytest.raises(ValueError):
        validate_error_budget(excessive)


def test_missing_and_extra_fields_or_header_overflow_rejected(tmp_path: Path) -> None:
    request = command(tmp_path)
    fields = request.model_dump(mode="json")
    del fields["root"]
    with pytest.raises(ValueError):
        decode_command(frame(json.dumps(fields).encode(), b"evidence"))
    assert request.metadata is not None
    huge_meta = request.metadata.model_copy(
        update={"content_schema": "s" * MAX_HEADER_BYTES}
    )
    huge_ref = request.reference.model_copy(
        update={"content_schema": huge_meta.content_schema}
    )
    with pytest.raises(ValueError, match="framing"):
        encode_command(
            request.model_copy(update={"metadata": huge_meta, "reference": huge_ref}),
            b"evidence",
        )
