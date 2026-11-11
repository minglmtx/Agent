"""Strict scope/framing before storage effects; no legacy/default acceptance."""

import struct
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.adapters.storage.registered_protocol import (
    RegisteredStorageCommand,
    encode_registered_command,
    decode_registered_command,
)
from registered_storage_fixtures import request


@pytest.mark.parametrize(
    "create,reading,payload",
    [(True, False, b""), (False, False, b"evidence"), (False, True, b"")],
)
def test_exact_round_trip(
    tmp_path: Path, create: bool, reading: bool, payload: bytes
) -> None:
    cmd = request(tmp_path, create=create, reading=reading)
    assert decode_registered_command(encode_registered_command(cmd, payload)) == (
        cmd,
        payload,
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "bad", ["", "relative", "/tmp/../x", "/tmp//x", "/tmp/x/", "/tmp/\0x", "/tmp/a\\b"]
)
def test_root_paths_rejected(tmp_path: Path, bad: str) -> None:
    config = request(tmp_path).config
    with pytest.raises(ValidationError):
        EvidenceStorageConfig.model_validate(
            config.model_copy(update={"evidence_root": bad})
        )


@pytest.mark.parametrize("field", ["source_task_id", "storage_config_sha256", "scope"])
def test_binding_mismatch_rejected(tmp_path: Path, field: str) -> None:
    cmd = request(tmp_path)
    change = {
        "source_task_id": None,
        "storage_config_sha256": "0" * 64,
        "scope": "run",
    }[field]
    with pytest.raises(ValidationError):
        RegisteredStorageCommand.model_validate(
            cmd.model_copy(
                update={"binding": cmd.binding.model_copy(update={field: change})}
            )
        )


@pytest.mark.parametrize(
    "fault",
    [
        "parent",
        "owner",
        "attempt",
        "root",
        "limit",
        "revision",
        "create_payload",
        "wrong_payload",
    ],
)
def test_no_implicit_parameters(tmp_path: Path, fault: str) -> None:
    cmd = request(tmp_path)
    assert cmd.io is not None
    change: dict[str, object] = {}
    if fault in ("parent", "owner", "attempt"):
        key = {
            "parent": "parent_operation_id",
            "owner": "owner_id",
            "attempt": "attempt_id",
        }[fault]
        change = {"operation": cmd.operation.model_copy(update={key: "other"})}
    elif fault in ("root", "limit"):
        change = {
            "io": cmd.io.model_copy(
                update=(
                    {"root": str(tmp_path / "other")}
                    if fault == "root"
                    else {"max_object_bytes": 10}
                )
            )
        }
    elif fault == "revision":
        change = {"expected_revision": None}
    if change:
        with pytest.raises(ValidationError):
            RegisteredStorageCommand.model_validate(cmd.model_copy(update=change))
    else:
        with pytest.raises(ValueError):
            encode_registered_command(
                request(tmp_path, create=fault == "create_payload"), b"wrong"
            )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\0" * 4,
        struct.pack(">I", 65537),
        struct.pack(">I", 2) + b"{}",
        b"no header",
    ],
)
def test_bad_frames_fail(raw: bytes) -> None:
    with pytest.raises(ValueError):
        decode_registered_command(raw)


def test_duplicate_json_and_wrong_type_fail(tmp_path: Path) -> None:
    raw = encode_registered_command(request(tmp_path, create=True))
    n = struct.unpack(">I", raw[:4])[0]
    header = raw[4 : 4 + n].replace(b"{", b'{"action":"create",', 1)
    with pytest.raises(ValueError):
        decode_registered_command(struct.pack(">I", len(header)) + header)
    with pytest.raises((TypeError, ValueError)):
        decode_registered_command(cast(bytes, bytearray(raw)))
