"""Real frozen files and CAS with synthetic components, never runtime approval."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.releases.documents import EvidenceReleaseDocuments
from lab_generate_skill.adapters.releases.files_port import FrozenReleaseFiles
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.release.candidates import ReleaseCandidates
from registry_fixtures import Fixture, fixture


@dataclass
class CandidateFixture:
    root: Path
    metadata: Fixture
    store: FileEvidenceStore
    documents: EvidenceReleaseDocuments
    files: FrozenReleaseFiles
    candidates: ReleaseCandidates


def setup(root: Path) -> CandidateFixture:
    metadata = fixture(root)
    raw = metadata.index.model_dump_json().encode()
    for artifact in metadata.release.artifacts:
        for entry in artifact.files:
            path = Path(artifact.root) / entry.path
            path.parent.mkdir(parents=True, exist_ok=True)
            data = (
                raw
                if entry.path == "registry.json"
                else (b"run" if entry.executable else b"code")
            )
            path.write_bytes(data)
            path.chmod(0o555 if entry.executable else 0o444)
        directories = [p for p in Path(artifact.root).rglob("*") if p.is_dir()]
        for path in sorted(directories, key=lambda p: len(p.parts), reverse=True):
            path.chmod(0o555)
        Path(artifact.root).chmod(0o555)
    store_root = root / "cas"
    store_root.mkdir()
    store = FileEvidenceStore(store_root)
    stored = store.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="task-registry/1",
            visibility="private",
            producer="unit-registry",
        ),
    )
    assert stored == metadata.reference
    documents = EvidenceReleaseDocuments(store)
    files = FrozenReleaseFiles(root)
    return CandidateFixture(
        root, metadata, store, documents, files, ReleaseCandidates(documents, files)
    )


def writable(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)


def blobs(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in (root / "cas/blobs").iterdir()}
