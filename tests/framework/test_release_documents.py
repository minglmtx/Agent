"""Document adapter boundary checks, including dishonest store return values."""

from lab_generate_skill.ports.lifecycle import OperationControl

from pathlib import Path
import pytest
from lab_generate_skill.adapters.releases.documents import EvidenceReleaseDocuments
from lab_generate_skill.adapters.releases.files_port import FrozenReleaseFiles
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.release_candidate import candidate_reference
from release_fixtures import manifest
from test_slurm_commands import guard


class NoReadStore:
    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        raise AssertionError("invalid reference must be rejected before read")

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        raise AssertionError("invalid input must be rejected before write")


@pytest.mark.parametrize("kind", ["registry", "manifest"])
@pytest.mark.parametrize("fault", ["zero", "oversize", "public", "schema"])
def test_reference_validation_precedes_storage(
    tmp_path: Path, kind: str, fault: str
) -> None:
    ref = candidate_reference(manifest(tmp_path / "files"))
    ref = ref.model_copy(
        update={
            "content_schema": (
                "task-registry/1" if kind == "registry" else "release-manifest/1"
            )
        }
    )
    if fault == "zero":
        ref = ref.model_copy(update={"size_bytes": 0})
    elif fault == "oversize":
        ref = ref.model_copy(update={"size_bytes": 32 * 1024 * 1024 + 1})
    elif fault == "public":
        ref = ref.model_copy(update={"visibility": "public"})
    else:
        ref = ref.model_copy(update={"content_schema": "old/1"})
    documents = EvidenceReleaseDocuments(NoReadStore())
    method = documents.registry if kind == "registry" else documents.manifest
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        method(ref, guard())


def test_store_return_cannot_change_manifest_identity(tmp_path: Path) -> None:
    m = manifest(tmp_path / "files")

    class WrongStore(NoReadStore):
        def put(
            self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            return candidate_reference(m.model_copy(update={"release_id": "wrong"}))

    with pytest.raises(EvidenceIntegrityError, match="another reference"):
        EvidenceReleaseDocuments(WrongStore()).put(m, guard())


def test_relative_workspace_rejected_before_io() -> None:
    with pytest.raises(ValueError, match="absolute"):
        FrozenReleaseFiles(Path("relative"))
