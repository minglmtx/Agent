"""Persistence failure/receipt loss: never infer that original intent did not commit."""

import os
from pathlib import Path
import pytest
from lab_generate_skill.domain.evidence_session_commit import (
    EvidenceSessionCommitUnconfirmed,
)
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from evidence_session_fixtures import binding, capacity, intent
from evidence_session_storage_fixtures import store, snapshot_path
from test_atomic_snapshot import flatten


@pytest.mark.parametrize("target", ["write", "fsync", "replace"])
def test_commit_failure_preserves_old_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    ledger = store(tmp_path)
    original = intent()
    b = binding()
    ledger.create(b, capacity(), original.operation)
    before = snapshot_path(tmp_path).read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("unit " + target)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, target, fail)
        with pytest.raises(EvidenceSessionCommitUnconfirmed) as failure:
            ledger.begin(b, original, 0)
    assert failure.value.candidate.entries[0].intent == original
    assert isinstance(failure.value.__cause__, OSError)
    assert snapshot_path(tmp_path).read_bytes() == before
    assert not list(tmp_path.glob(".pending-snapshot-*"))


def test_publication_then_lost_ack_never_reissues_begin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = store(tmp_path)
    original = intent()
    b = binding()
    ledger.create(b, capacity(), original.operation)
    real = os.replace

    def replace_then_fail(*args: object, **kwargs: object) -> None:
        real(*args, **kwargs)  # type: ignore[arg-type]
        raise OSError("unit lost confirmation")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", replace_then_fail)
        with pytest.raises(EvidenceSessionCommitUnconfirmed):
            ledger.begin(b, original, 0)
    assert store(tmp_path).read(b, original.operation).entries[0].intent == original
    with pytest.raises(DispatchAlreadyCommitted):
        store(tmp_path).begin(b, original, 0)


def test_primary_and_all_cleanup_errors_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = store(tmp_path)
    original = intent()
    b = binding()
    ledger.create(b, capacity(), original.operation)
    before = snapshot_path(tmp_path).read_bytes()
    realclose = os.close

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError("primary replace")

    def fail_unlink(*args: object, **kwargs: object) -> None:
        raise OSError("cleanup unlink")

    def close_then_fail(fd: int) -> None:
        temporary = ".pending-snapshot-" in os.readlink(f"/proc/self/fd/{fd}")
        realclose(fd)
        if temporary:
            raise OSError("cleanup close")

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", fail_replace)
        scoped.setattr(os, "unlink", fail_unlink)
        scoped.setattr(os, "close", close_then_fail)
        with pytest.raises(EvidenceSessionCommitUnconfirmed) as failure:
            ledger.begin(b, original, 0)
    assert failure.value.__cause__ is not None
    assert [str(e) for e in flatten(failure.value.__cause__)] == [
        "primary replace",
        "cleanup unlink",
        "cleanup close",
    ]
    assert snapshot_path(tmp_path).read_bytes() == before
    assert len(list(tmp_path.glob(".pending-snapshot-*"))) == 1
