"""Failed commit/readback retains exact original evidence and exception chain."""

from collections.abc import Iterator
from pathlib import Path
import os
import pytest
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.release_candidate import (
    CandidateCommitObservation,
    candidate_reference,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from release_candidate_fixtures import CandidateFixture, setup, writable, blobs
from test_slurm_commands import guard


@pytest.fixture
def case(tmp_path: Path) -> Iterator[CandidateFixture]:
    try:
        yield setup(tmp_path)
    finally:
        writable(tmp_path)


@pytest.mark.parametrize("after", [False, True])
def test_put_failure_retains_first_and_cleanup_and_original_bytes(
    case: CandidateFixture, monkeypatch: pytest.MonkeyPatch, after: bool
) -> None:
    original = case.documents.put
    error = ExceptionGroup("commit and cleanup", [OSError("primary"), OSError("close")])

    def fail(manifest: ReleaseManifest, control: OperationControl) -> EvidenceRef:
        if after:
            original(manifest, control)
        raise error

    monkeypatch.setattr(case.documents, "put", fail)
    m = case.metadata
    with pytest.raises(ExceptionGroup) as caught:
        case.candidates.stage(m.release, m.reference, m.supported, guard())
    assert caught.value is error
    observation = getattr(error, "release_candidate")
    assert isinstance(observation, CandidateCommitObservation)
    assert observation.phase == "put"
    assert observation.candidate.manifest_ref == candidate_reference(m.release)
    assert len(blobs(case.root)) == (2 if after else 1)
    monkeypatch.setattr(case.documents, "put", original)
    result = case.candidates.stage(m.release, m.reference, m.supported, guard())
    assert result == observation.candidate
    assert len(blobs(case.root)) == 2


@pytest.mark.parametrize("fault", ["io", "different", "cancel"])
def test_readback_failure_preserves_committed_manifest(
    case: CandidateFixture, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    m = case.metadata

    def read(reference: EvidenceRef, control: OperationControl) -> ReleaseManifest:
        if fault == "io":
            raise OSError("readback unavailable")
        if fault == "cancel":
            guard(-1).checkpoint()
        return m.release.model_copy(update={"release_id": "another-release"})

    monkeypatch.setattr(case.documents, "manifest", read)
    with pytest.raises((OSError, EvidenceIntegrityError, OperationStopped)) as caught:
        case.candidates.stage(m.release, m.reference, m.supported, guard())
    observation = getattr(caught.value, "release_candidate")
    assert observation.phase == "readback"
    assert (
        case.store.read(observation.candidate.manifest_ref)
        == m.release.model_dump_json().encode()
    )
    assert len(blobs(case.root)) == 2


def test_wrong_put_reference_cannot_succeed(
    case: CandidateFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def wrong(manifest: ReleaseManifest, control: OperationControl) -> EvidenceRef:
        return case.metadata.reference

    monkeypatch.setattr(case.documents, "put", wrong)
    m = case.metadata
    with pytest.raises(EvidenceIntegrityError) as caught:
        case.candidates.stage(m.release, m.reference, m.supported, guard())
    assert getattr(caught.value, "release_candidate").phase == "put"
    assert len(blobs(case.root)) == 1


@pytest.mark.parametrize("sync_number", [1, 2])
def test_real_cas_sync_failure_retains_disk_for_exact_reconciliation(
    case: CandidateFixture, monkeypatch: pytest.MonkeyPatch, sync_number: int
) -> None:
    original_sync = os.fsync
    calls = 0

    def fail(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == sync_number:
            raise OSError("injected candidate sync failure")
        original_sync(fd)

    monkeypatch.setattr(os, "fsync", fail)
    m = case.metadata
    with pytest.raises(OSError, match="injected candidate sync failure") as caught:
        case.candidates.stage(m.release, m.reference, m.supported, guard())
    observation = getattr(caught.value, "release_candidate")
    assert observation.phase == "put"
    # File sync fails before publication; directory sync fails after the link.
    assert len(blobs(case.root)) == (1 if sync_number == 1 else 2)
    assert not any(name.startswith(".") for name in blobs(case.root))
    monkeypatch.setattr(os, "fsync", original_sync)
    assert (
        case.candidates.stage(m.release, m.reference, m.supported, guard())
        == observation.candidate
    )
    assert len(blobs(case.root)) == 2


def test_final_stop_after_confirmed_readback_does_not_return_success(
    case: CandidateFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StopAfterReadback:
        stopped = False

        def checkpoint(self) -> float:
            if self.stopped:
                guard(-1).checkpoint()
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    control = StopAfterReadback()
    original = case.documents.manifest

    def read(reference: EvidenceRef, op: OperationControl) -> ReleaseManifest:
        result = original(reference, op)
        control.stopped = True
        return result

    monkeypatch.setattr(case.documents, "manifest", read)
    m = case.metadata
    with pytest.raises(OperationStopped) as caught:
        case.candidates.stage(m.release, m.reference, m.supported, control)
    observation = getattr(caught.value, "release_candidate")
    assert observation.phase == "confirmed"
    assert (
        case.store.read(observation.candidate.manifest_ref)
        == m.release.model_dump_json().encode()
    )
    assert len(blobs(case.root)) == 2
