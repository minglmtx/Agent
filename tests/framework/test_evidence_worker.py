"""Actual worker CAS, pre-effect rejection, failure topology and module entry.

Subprocess tests explicitly bind the development source path; they do not count
as immutable-release installation, process supervision or durable isolation.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

from lab_generate_skill.adapters.storage.evidence_worker import exchange
from lab_generate_skill.adapters.storage.worker_protocol import (
    decode_reply,
    encode_command,
)
from evidence_worker_fixtures import command


@pytest.mark.parametrize("data", [b"", b"\0\xffbinary", b"bytes" * 13000])
def test_worker_put_read_and_exact_repeat(tmp_path: Path, data: bytes) -> None:
    put = command(tmp_path, data)
    reply, payload = decode_reply(put, exchange(encode_command(put, data)))
    assert reply.error is None and payload == b""
    blob = tmp_path / "blobs" / put.reference.sha256
    inode = blob.stat().st_ino
    assert decode_reply(put, exchange(encode_command(put, data)))[0] == reply
    assert blob.stat().st_ino == inode and blob.read_bytes() == data
    read = command(tmp_path, data, "read")
    result, payload = decode_reply(read, exchange(encode_command(read)))
    assert result.error is None and payload == data
    assert len(list((tmp_path / "blobs").iterdir())) == 1


def test_invalid_input_never_opens_storage(tmp_path: Path) -> None:
    put = command(tmp_path)
    packet = encode_command(put, b"evidence")[:-1] + b"x"
    with patch(
        "lab_generate_skill.adapters.storage.evidence_worker.FileEvidenceStore"
    ) as store:
        with pytest.raises(ValueError):
            exchange(packet)
        store.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_missing_root_and_missing_object_are_distinct(tmp_path: Path) -> None:
    absent_root = command(tmp_path / "missing", operation="read")
    first, _ = decode_reply(absent_root, exchange(encode_command(absent_root)))
    assert first.error is not None and first.error.type_name == "FileNotFoundError"
    assert not (tmp_path / "missing").exists()
    (tmp_path / "blobs").mkdir()
    absent_blob = command(tmp_path, operation="read")
    second, _ = decode_reply(absent_blob, exchange(encode_command(absent_blob)))
    assert second.error is not None and second.error.type_name == "EvidenceNotFound"
    assert second.error.reason_code == "MISSING_EVIDENCE"


def test_read_does_not_initialize_or_sync_storage(tmp_path: Path) -> None:
    read = command(tmp_path, operation="read")
    with (
        patch.object(os, "mkdir", side_effect=AssertionError("read created directory")),
        patch.object(os, "fsync", side_effect=AssertionError("read called fsync")),
    ):
        reply, body = decode_reply(read, exchange(encode_command(read)))
    assert reply.error is not None and reply.error.type_name == "EvidenceIntegrityError"
    assert not body and list(tmp_path.iterdir()) == []
    put = command(tmp_path)
    exchange(encode_command(put, b"evidence"))
    with (
        patch.object(os, "mkdir", side_effect=AssertionError("read created directory")),
        patch.object(os, "fsync", side_effect=AssertionError("read called fsync")),
    ):
        reply, body = decode_reply(read, exchange(encode_command(read)))
    assert reply.error is None and body == b"evidence"


@pytest.mark.parametrize("damage", ["corrupt", "symlink", "fifo"])
def test_worker_refuses_damaged_blob_without_replacing(
    tmp_path: Path, damage: str
) -> None:
    put = command(tmp_path)
    exchange(encode_command(put, b"evidence"))
    blob = tmp_path / "blobs" / put.reference.sha256
    blob.unlink()
    if damage == "corrupt":
        blob.write_bytes(b"bad")
    elif damage == "symlink":
        outside = tmp_path / "outside"
        outside.write_bytes(b"evidence")
        blob.symlink_to(outside)
    else:
        os.mkfifo(blob)
    inode = blob.lstat().st_ino
    read = command(tmp_path, operation="read")
    for request, payload in ((read, b""), (put, b"evidence")):
        result, body = decode_reply(request, exchange(encode_command(request, payload)))
        assert (
            result.error is not None
            and result.error.type_name == "EvidenceIntegrityError"
        )
        assert body == b"" and blob.lstat().st_ino == inode


def test_primary_and_cleanup_errors_survive_wire_protocol(tmp_path: Path) -> None:
    put = command(tmp_path)
    with (
        patch.object(os, "link", side_effect=OSError(5, "publication")),
        patch.object(os, "unlink", side_effect=PermissionError(13, "cleanup")),
    ):
        result, body = decode_reply(put, exchange(encode_command(put, b"evidence")))
    assert not body and result.error is not None
    assert result.error.type_name == "ExceptionGroup"
    assert [x.errno for x in result.error.children] == [5, 13]
    pending = list((tmp_path / "blobs").iterdir())
    assert len(pending) == 1 and pending[0].name.startswith(".pending-")
    assert pending[0].read_bytes() == b"evidence"


def test_postpublication_error_retains_expected_identity_and_actual_blob(
    tmp_path: Path,
) -> None:
    put = command(tmp_path)
    original = os.fsync
    count = 0

    def fail_publication_ack(fd: int) -> None:
        nonlocal count
        count += 1
        original(fd)
        if count == 3:
            raise OSError(5, "publication acknowledgement lost")

    with patch.object(os, "fsync", side_effect=fail_publication_ack):
        result, body = decode_reply(put, exchange(encode_command(put, b"evidence")))
    assert result.error is not None and result.reference == put.reference and not body
    assert (tmp_path / "blobs" / put.reference.sha256).read_bytes() == b"evidence"
    read = command(tmp_path, operation="read")
    assert decode_reply(read, exchange(encode_command(read)))[1] == b"evidence"


def run_module(raw: bytes) -> subprocess.CompletedProcess[bytes]:
    source = Path(__file__).resolve().parents[2] / "src"
    return subprocess.run(
        [
            sys.executable,
            "-P",
            "-B",
            "-m",
            "lab_generate_skill.adapters.storage.evidence_worker",
        ],
        input=raw,
        capture_output=True,
        timeout=10,
        env={"PYTHONPATH": str(source), "PATH": "/usr/bin:/bin", "LANG": "C"},
    )


def test_actual_module_entry_and_new_process_readback(tmp_path: Path) -> None:
    put = command(tmp_path)
    first = run_module(encode_command(put, b"evidence"))
    assert first.returncode == 0 and first.stderr == b""
    assert decode_reply(put, first.stdout)[0].error is None
    read = command(tmp_path, operation="read")
    second = run_module(encode_command(read))
    assert second.returncode == 0 and second.stderr == b""
    assert decode_reply(read, second.stdout)[1] == b"evidence"


def test_module_invalid_input_exits_without_echo_or_disk_effects(
    tmp_path: Path,
) -> None:
    secret = b"sensitive malformed input"
    result = run_module(secret)
    assert result.returncode == 2 and not result.stdout
    assert secret not in result.stderr
    assert result.stderr == b"EVIDENCE_WORKER_PROTOCOL_OR_OUTPUT_FAILED\n"
    assert list(tmp_path.iterdir()) == []
