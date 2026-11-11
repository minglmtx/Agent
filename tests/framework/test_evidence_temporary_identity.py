"""Exact scratch identity, no foreign deletion and actual crash leftovers.

These checks use the raw worker, not the completed supervised-storage assembly.
No test treats knowing a pathname or a child exit as recovery authorization.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.storage.evidence_worker import exchange
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.adapters.storage.temporary_identity import (
    exchange_temporary_name,
)
from lab_generate_skill.adapters.storage.worker_protocol import (
    encode_command,
    decode_reply,
)
from evidence_worker_fixtures import command


@pytest.mark.parametrize("identity", ["a", "source:exchange-1", "a" * 256])
def test_name_is_stable_bounded_and_exchange_specific(identity: str) -> None:
    name = exchange_temporary_name(identity)
    assert name == exchange_temporary_name(identity)
    assert len(name) == len(".pending-exchange-") + 64
    assert "/" not in name and "\\" not in name
    assert name != exchange_temporary_name("different-" + identity[:200])


@pytest.mark.parametrize(
    "invalid", ["", "a" * 257, "../a", "a/b", "a\0b", "é", 3, False, [], b"a"]
)
def test_invalid_identity_rejected_before_file_effect(
    tmp_path: Path, invalid: object
) -> None:
    put = command(tmp_path)
    assert put.metadata is not None
    store = FileEvidenceStore(tmp_path)
    with pytest.raises(ValidationError):
        store.put(b"evidence", put.metadata, exchange_id=cast(str, invalid))
    assert list((tmp_path / "blobs").iterdir()) == []


@pytest.mark.parametrize("symlink", [False, True])
def test_collision_never_deletes_or_changes_prior_temporary(
    tmp_path: Path, symlink: bool
) -> None:
    put = command(tmp_path)
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    prior = blobs / exchange_temporary_name(put.exchange_id)
    outside = tmp_path / "outside"
    outside.write_bytes(b"prior-owner")
    if symlink:
        prior.symlink_to(outside)
    else:
        prior.write_bytes(b"prior-owner")
    before = prior.lstat()
    for _ in range(2):
        reply, body = decode_reply(put, exchange(encode_command(put, b"evidence")))
        assert not body and reply.error is not None
        assert reply.error.type_name == "FileExistsError"
        assert prior.lstat().st_ino == before.st_ino
        assert prior.read_bytes() == outside.read_bytes() == b"prior-owner"
        assert not (blobs / put.reference.sha256).exists()
    other = put.model_copy(update={"exchange_id": "other-exchange"})
    reply, _ = decode_reply(other, exchange(encode_command(other, b"evidence")))
    assert reply.error is None and prior.lstat().st_ino == before.st_ino


def test_combined_publication_and_cleanup_failure_retains_named_original(
    tmp_path: Path,
) -> None:
    put = command(tmp_path)
    with (
        patch.object(os, "link", side_effect=OSError(5, "publish")),
        patch.object(os, "unlink", side_effect=PermissionError(13, "cleanup")),
    ):
        reply, _ = decode_reply(put, exchange(encode_command(put, b"evidence")))
    assert reply.error is not None
    assert [e.errno for e in reply.error.children] == [5, 13]
    blobs = tmp_path / "blobs"
    assert [p.name for p in blobs.iterdir()] == [
        exchange_temporary_name(put.exchange_id)
    ]
    assert (
        blobs / exchange_temporary_name(put.exchange_id)
    ).read_bytes() == b"evidence"


@pytest.mark.parametrize("published", [False, True])
def test_hard_exit_leaves_exact_original_temporary(
    tmp_path: Path, published: bool
) -> None:
    put = command(tmp_path)
    # Real os._exit bypasses Python finally. No production callback is exposed.
    code = """
import os, sys
from lab_generate_skill.adapters.storage.evidence_worker import exchange
original = os.link
def crash(*args, **kwargs):
    if sys.argv[1] == "published":
        original(*args, **kwargs)
    os._exit(91)
os.link = crash
exchange(sys.stdin.buffer.read())
"""
    source = Path(__file__).resolve().parents[2] / "src"
    child = subprocess.run(
        [
            sys.executable,
            "-P",
            "-B",
            "-c",
            code,
            "published" if published else "unpublished",
        ],
        input=encode_command(put, b"evidence"),
        capture_output=True,
        timeout=10,
        env={"PYTHONPATH": str(source), "PATH": "/usr/bin:/bin", "LANG": "C"},
    )
    assert child.returncode == 91 and child.stdout == b"" and child.stderr == b""
    blobs = tmp_path / "blobs"
    assert (
        blobs / exchange_temporary_name(put.exchange_id)
    ).read_bytes() == b"evidence"
    assert (blobs / put.reference.sha256).exists() is published
    # Raw primitive refuses an existing scratch file; it cannot infer clean or
    # retry success from the committed blob. Registered dispatch is stricter.
    reply, _ = decode_reply(put, exchange(encode_command(put, b"evidence")))
    assert reply.error is not None and reply.error.type_name == "FileExistsError"
