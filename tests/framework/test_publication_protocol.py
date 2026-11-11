"""Packet bounds, exact commands and non-interchangeable observed identities."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.publication_protocol import (
    encode_publication_command,
    decode_publication_command,
    encode_publication_reply,
    decode_publication_reply,
    MAX_REQUEST,
)
from publication_worker_fixtures import inputs, reply


def test_exact_roundtrip(tmp_path: Path) -> None:
    _, snapshot, command = inputs(tmp_path)
    raw = encode_publication_command(command)
    assert decode_publication_command(raw) == command
    observed = reply(command, snapshot)
    assert decode_publication_reply(raw, encode_publication_reply(observed)) == observed


@pytest.mark.parametrize(
    "bad", [b"", b"{}", b"[]", b'{"x":1,"x":2}', b"null", b"NaN", b"\xff", b"{}\n{}"]
)
def test_invalid_command(bad: bytes) -> None:
    with pytest.raises(ValueError):
        decode_publication_command(bad)


def test_oversized_packet() -> None:
    with pytest.raises(ValueError):
        decode_publication_command(b" " * (MAX_REQUEST + 1))


@pytest.mark.parametrize(
    "case",
    [
        "version",
        "digest",
        "parent",
        "host",
        "deployment",
        "source",
        "membership",
        "uid",
        "phase",
        "missing_snapshot",
        "missing_installation",
        "missing_membership",
        "extra",
    ],
)
def test_reply_mismatch(tmp_path: Path, case: str) -> None:
    _, snapshot, command = inputs(tmp_path)
    data = reply(command, snapshot).model_dump(mode="json")
    if case == "version":
        data["schema_version"] = "publication-read-reply/0"
    elif case == "digest":
        data["command_sha256"] = "0" * 64
    elif case == "parent":
        data["worker"]["process_id"] = command.scope.writer.process_id
    elif case == "host":
        data["worker"]["node_id"] = "other"
    elif case == "deployment":
        data["snapshot"]["deployment"]["deployment_id"] = "other"
    elif case == "source":
        data["installed_sources"]["manifest_sha256"] = "0" * 64
    elif case == "membership":
        data["membership"]["writer"]["start_ticks"] += 1
    elif case == "uid":
        data["membership"]["uid"] += 1
    elif case == "phase":
        data["phase"] = "read"
    elif case == "missing_snapshot":
        data["snapshot"] = None
    elif case == "missing_installation":
        data["installed_sources"] = None
    elif case == "missing_membership":
        data["membership"] = None
    else:
        data["unknown"] = True
    with pytest.raises(ValueError):
        decode_publication_reply(
            encode_publication_command(command), json.dumps(data).encode()
        )
