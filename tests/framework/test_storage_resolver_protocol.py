"""Original cleanup identity, ending provenance, bounded and strict framing."""

import hashlib
import struct
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from lab_generate_skill.adapters.storage.registered_protocol import (
    encode_registered_command,
)
from lab_generate_skill.adapters.storage.resolver_protocol import (
    StorageResolutionCommand,
    encode_resolution_command,
    decode_resolution_command,
)
from registered_storage_fixtures import request


def resolution(root: Path) -> StorageResolutionCommand:
    original = request(root)
    ending = StorageProcessEnd(
        controller=original.controller,
        request_sha256=hashlib.sha256(
            encode_registered_command(original, b"evidence")
        ).hexdigest(),
        process_id=original.controller.process_id + 1,
        returncode=0,
        observed_at=datetime.now(timezone.utc),
        capture_sha256="a" * 64,
        kill_requested=False,
    )
    return StorageResolutionCommand(
        original=original,
        cleanup=original.operation.cleanup(
            "close", now=datetime.now(timezone.utc), seconds=30
        ),
        ending=ending,
    )


def test_exact_roundtrip(tmp_path: Path) -> None:
    cmd = resolution(tmp_path)
    for ending in (cmd.ending, None):
        value = cmd.model_copy(update={"ending": ending})
        assert decode_resolution_command(
            encode_resolution_command(value, b"evidence")
        ) == (value, b"evidence")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "fault",
    [
        "create",
        "execute",
        "parent",
        "owner",
        "attempt",
        "controller",
        "digest",
        "payload",
        "missing_ending_field",
    ],
)
def test_wrong_lineage_fails_before_any_io(tmp_path: Path, fault: str) -> None:
    cmd = resolution(tmp_path)
    ending = cmd.ending
    assert ending is not None
    if fault == "create":
        cmd = cmd.model_copy(update={"original": request(tmp_path, create=True)})
    elif fault in ("execute", "parent", "owner", "attempt"):
        changes: dict[str, dict[str, object]] = {
            "execute": {"mode": "execute", "parent_operation_id": None},
            "parent": {"parent_operation_id": "wrong"},
            "owner": {"owner_id": "wrong"},
            "attempt": {"attempt_id": "wrong"},
        }
        cmd = cmd.model_copy(
            update={"cleanup": cmd.cleanup.model_copy(update=changes[fault])}
        )
    elif fault == "controller":
        cmd = cmd.model_copy(
            update={
                "ending": ending.model_copy(
                    update={
                        "controller": ending.controller.model_copy(
                            update={"start_ticks": ending.controller.start_ticks + 1}
                        )
                    }
                )
            }
        )
    elif fault == "digest":
        cmd = cmd.model_copy(
            update={"ending": ending.model_copy(update={"request_sha256": "0" * 64})}
        )
    if fault == "missing_ending_field":
        raw = cmd.model_dump()
        del raw["ending"]
        with pytest.raises(ValidationError):
            StorageResolutionCommand.model_validate(raw)
    else:
        with pytest.raises(ValueError):
            encode_resolution_command(
                cmd, b"wrong" if fault == "payload" else b"evidence"
            )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "raw",
    [b"", b"broken", b"\0" * 4, struct.pack(">I", 65537), struct.pack(">I", 2) + b"{}"],
)
def test_invalid_frames_fail(raw: bytes) -> None:
    with pytest.raises(ValueError):
        decode_resolution_command(raw)
