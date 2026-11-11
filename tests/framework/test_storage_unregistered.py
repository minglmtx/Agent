"""Absence is a versioned factual proof, not an original I/O success or retry."""

import hashlib
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.storage_unregistered import StorageUnregisteredExchange
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.adapters.processes.worker_identity import (
    current_evidence_worker,
)
from lab_generate_skill.adapters.storage.resolver_protocol import (
    StorageResolutionReply,
    StorageResolutionCommand,
)
from test_storage_resolver_protocol import resolution


def case(
    root: Path,
) -> tuple[
    StorageResolutionCommand, EvidenceSessionSnapshot, StorageUnregisteredExchange
]:
    cmd = resolution(root)
    assert cmd.ending is not None and cmd.original.io is not None
    observer = current_evidence_worker().model_copy(
        update={"process_id": cmd.original.controller.process_id + 2}
    )
    snapshot = EvidenceSessionSnapshot(
        binding=cmd.original.binding, capacity=cmd.original.config.capacity, entries=()
    )
    proof = StorageUnregisteredExchange(
        exchange_id=cmd.original.io.exchange_id,
        request_sha256=cmd.ending.request_sha256,
        binding=cmd.original.binding,
        operation=cmd.cleanup,
        ending=cmd.ending,
        observer=observer,
        revision=0,
        snapshot_sha256=hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest(),
    )
    return cmd, snapshot, proof


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "revision",
        "digest",
        "request",
        "exchange",
        "ending",
        "observer",
        "scope",
        "no_ending",
    ],
)
def test_exact_unregistered_proof_and_mismatches(tmp_path: Path, fault: str) -> None:
    cmd, snapshot, proof = case(tmp_path)
    assert cmd.original.io is not None
    altered = proof
    if fault == "revision":
        altered = proof.model_copy(update={"revision": 1})
    elif fault == "digest":
        altered = proof.model_copy(update={"snapshot_sha256": "0" * 64})
    elif fault == "request":
        altered = proof.model_copy(update={"request_sha256": "0" * 64})
    elif fault == "exchange":
        altered = proof.model_copy(update={"exchange_id": "foreign"})
    elif fault == "ending":
        altered = proof.model_copy(
            update={"ending": proof.ending.model_copy(update={"returncode": 9})}
        )
    elif fault == "observer":
        altered = proof.model_copy(
            update={
                "observer": proof.observer.model_copy(
                    update={"process_id": proof.observer.process_id + 1}
                )
            }
        )
    elif fault == "scope":
        altered = proof.model_copy(
            update={
                "binding": proof.binding.model_copy(update={"session_id": "foreign"})
            }
        )

    def check() -> None:
        assert cmd.original.io is not None
        altered.check(
            snapshot,
            exchange_id=cmd.original.io.exchange_id,
            request_sha256=proof.request_sha256,
            binding=cmd.original.binding,
            operation=cmd.cleanup,
            ending=None if fault == "no_ending" else cmd.ending,
            observer=proof.observer,
            expected_revision=0,
        )

    if fault == "none":
        check()
        check()
    else:
        with pytest.raises(ValueError, match="original ended request/history"):
            check()


def test_absence_reply_is_explicit_v4_and_legacy_v3_bytes_keep_old_fields(
    tmp_path: Path,
) -> None:
    _, _, proof = case(tmp_path)
    old = StorageResolutionReply(
        request_sha256="a" * 64, worker=proof.observer, phase="original_history"
    )
    assert "not_registered" not in old.model_dump()
    assert StorageResolutionReply.model_validate_json(old.model_dump_json()) == old
    current = StorageResolutionReply(
        schema_version="storage-resolution-reply/4",
        request_sha256="a" * 64,
        worker=proof.observer,
        phase="completion",
        not_registered=proof,
    )
    assert (
        StorageResolutionReply.model_validate_json(current.model_dump_json()) == current
    )
    for update in (
        {"schema_version": "storage-resolution-reply/3"},
        {"not_registered": None},
        {"phase": "original_history"},
    ):
        with pytest.raises(ValidationError):
            StorageResolutionReply.model_validate(current.model_copy(update=update))


@pytest.mark.parametrize("revision", [None, True, "0", -1])
def test_missing_wrong_or_negative_revision_rejected(
    tmp_path: Path, revision: object
) -> None:
    _, _, proof = case(tmp_path)
    with pytest.raises(ValidationError):
        StorageUnregisteredExchange.model_validate(
            {**proof.model_dump(), "revision": revision}
        )
