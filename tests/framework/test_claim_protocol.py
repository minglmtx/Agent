"""Packet bounds, exact commands and non-interchangeable observed identities."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.claim_protocol import (
    encode_claim_command,
    decode_claim_command,
    encode_claim_reply,
    decode_claim_reply,
    MAX_REQUEST,
)
from claim_worker_fixtures import inputs, reply


def test_exact_roundtrip(tmp_path: Path) -> None:
    _, record, command = inputs(tmp_path)
    raw = encode_claim_command(command)
    assert decode_claim_command(raw) == command
    observed = reply(command, record)
    assert decode_claim_reply(raw, encode_claim_reply(observed)) == observed


@pytest.mark.parametrize(
    "bad", [b"", b"{}", b"[]", b'{"x":1,"x":2}', b"null", b"NaN", b"\xff", b"{}\n{}"]
)
def test_invalid_command(bad: bytes) -> None:
    with pytest.raises(ValueError):
        decode_claim_command(bad)


def test_oversized_packet() -> None:
    with pytest.raises(ValueError):
        decode_claim_command(b" " * (MAX_REQUEST + 1))


@pytest.mark.parametrize(
    "case",
    [
        "version",
        "digest",
        "parent",
        "host",
        "binding",
        "private_task",
        "source",
        "membership",
        "uid",
        "phase",
        "missing_record",
        "missing_installation",
        "missing_membership",
        "extra",
    ],
)
def test_reply_mismatch(tmp_path: Path, case: str) -> None:
    _, record, command = inputs(tmp_path)
    data = reply(command, record).model_dump(mode="json")
    if case == "version":
        data["schema_version"] = "claim-read-reply/0"
    elif case == "digest":
        data["command_sha256"] = "0" * 64
    elif case == "parent":
        data["worker"]["process_id"] = command.scope.writer.process_id
    elif case == "host":
        data["worker"]["node_id"] = "other"
    elif case == "binding":
        data["record"]["binding"]["scope_id"] = "other"
    elif case == "private_task":
        data["record"]["binding"]["task"]["registration_id"] = "different"
    elif case == "source":
        data["installed_sources"]["manifest_sha256"] = "0" * 64
    elif case == "membership":
        data["membership"]["writer"]["start_ticks"] += 1
    elif case == "uid":
        data["membership"]["uid"] += 1
    elif case == "phase":
        data["phase"] = "read"
    elif case == "missing_record":
        data["record"] = None
    elif case == "missing_installation":
        data["installed_sources"] = None
    elif case == "missing_membership":
        data["membership"] = None
    else:
        data["unknown"] = True
    with pytest.raises(ValueError):
        decode_claim_reply(encode_claim_command(command), json.dumps(data).encode())


@pytest.mark.parametrize(
    "case", ["run_scope", "operation", "root", "empty_scope", "version"]
)
def test_invalid_command_scope_rejected(tmp_path: Path, case: str) -> None:
    _, _, command = inputs(tmp_path)
    data = command.model_dump(mode="json")
    if case == "run_scope":
        data["scope"]["claim"] = None
        data["scope"]["binding"]["scope"] = "run"
        data["scope"]["binding"]["source_task_id"] = None
    elif case == "operation":
        data["operation"]["owner_id"] = "other"
    elif case == "root":
        data["root"] = command.scope.config.session_root
    elif case == "empty_scope":
        data["scope"] = {}
    else:
        data["schema_version"] = "claim-read-command/0"
    with pytest.raises((ValueError, RuntimeError)):
        decode_claim_command(json.dumps(data).encode())
