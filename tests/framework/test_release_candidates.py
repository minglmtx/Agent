"""Composition acceptance: registry + actual frozen assets + canonical CAS.

Synthetic site bodies exercise release wiring only, not a runnable five-site
release. Tests assert disk effects as well as returned values and exceptions.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.registration import SupportedInterface
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.release_candidate import candidate_reference
from release_candidate_fixtures import CandidateFixture, setup, writable, blobs
from test_slurm_commands import guard


@pytest.fixture
def case(tmp_path: Path) -> Iterator[CandidateFixture]:
    try:
        yield setup(tmp_path)
    finally:
        writable(tmp_path)


def test_actual_candidate_readback_repeat_and_no_activation(
    case: CandidateFixture,
) -> None:
    m = case.metadata
    before = blobs(case.root)
    first = case.candidates.stage(m.release, m.reference, m.supported, guard())
    assert first.manifest_ref == candidate_reference(m.release)
    assert first.registry_ref == m.reference
    assert case.documents.manifest(first.manifest_ref, guard()) == m.release
    after = blobs(case.root)
    assert len(after) == len(before) + 1
    assert case.candidates.stage(m.release, m.reference, m.supported, guard()) == first
    assert blobs(case.root) == after
    assert not (case.root / "system-current.json").exists()
    assert not (Path(m.release.artifacts[0].root).stat().st_mode & 0o222)


@pytest.mark.parametrize("bad", [None, {}, "", [], 1])
def test_illegal_manifest_has_no_storage_effect(
    case: CandidateFixture, bad: object
) -> None:
    before = blobs(case.root)
    with pytest.raises(ValueError):
        case.candidates.stage(
            cast(ReleaseManifest, bad),
            case.metadata.reference,
            case.metadata.supported,
            guard(),
        )
    assert blobs(case.root) == before


@pytest.mark.parametrize(
    "choice", ["empty", "list", "duplicate", "wrong_major", "missing"]
)
def test_supported_interface_boundary(case: CandidateFixture, choice: str) -> None:
    m = case.metadata
    selected = m.supported
    if choice == "empty":
        selected = ()
    elif choice == "list":
        selected = cast(tuple[SupportedInterface, ...], list(selected))
    elif choice == "duplicate":
        selected += selected[:1]
    elif choice == "wrong_major":
        selected = tuple(x.model_copy(update={"contract_major": 99}) for x in selected)
    else:
        selected = selected[1:]
    before = blobs(case.root)
    with pytest.raises(ValueError):
        case.candidates.stage(m.release, m.reference, selected, guard())
    assert blobs(case.root) == before


@pytest.mark.parametrize(
    "fault", ["missing", "corrupt", "wrong_schema", "public", "other_release"]
)
def test_registry_rejection_never_publishes_manifest(
    case: CandidateFixture, fault: str
) -> None:
    m = case.metadata
    ref, release = m.reference, m.release
    path = case.root / "cas/blobs" / ref.sha256
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"bad")
    elif fault == "wrong_schema":
        ref = ref.model_copy(update={"content_schema": "other/1"})
    elif fault == "public":
        ref = ref.model_copy(update={"visibility": "public"})
    else:
        release = release.model_copy(update={"release_id": "other-release"})
    before = blobs(case.root)
    with pytest.raises(
        (ValueError, EvidenceIntegrityError, EvidenceNotFound, OwnershipConflict)
    ):
        case.candidates.stage(release, ref, m.supported, guard())
    assert blobs(case.root) == before


@pytest.mark.parametrize("fault", ["missing", "corrupt", "extra", "writable"])
def test_file_failure_is_before_manifest_commit(
    case: CandidateFixture, fault: str
) -> None:
    m = case.metadata
    root = Path(m.release.artifacts[0].root)
    root.chmod(0o755)
    path = root / "module.py"
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.chmod(0o644)
        path.write_bytes(b"evil")
        path.chmod(0o444)
    elif fault == "extra":
        (root / "extra").write_bytes(b"x")
    else:
        path.chmod(0o644)
    root.chmod(0o555)
    before = blobs(case.root)
    with pytest.raises((EvidenceIntegrityError, FileNotFoundError)):
        case.candidates.stage(m.release, m.reference, m.supported, guard())
    assert blobs(case.root) == before


def test_stop_before_work_preserves_disk(case: CandidateFixture) -> None:
    before = blobs(case.root)
    with pytest.raises(OperationStopped):
        case.candidates.stage(
            case.metadata.release,
            case.metadata.reference,
            case.metadata.supported,
            guard(-1),
        )
    assert blobs(case.root) == before


def test_concurrent_identical_candidates_converge(case: CandidateFixture) -> None:
    def publish(_: int) -> EvidenceRef:
        m = case.metadata
        return case.candidates.stage(
            m.release, m.reference, m.supported, guard(20)
        ).manifest_ref

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(publish, range(2)))
    assert results[0] == results[1]
    assert len(blobs(case.root)) == 2
