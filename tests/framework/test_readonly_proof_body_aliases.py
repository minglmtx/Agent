"""Content reuse retains each full ref check and expires with the current proof."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from test_slurm_commands import guard


@pytest.mark.parametrize("fault", ["none", "size", "uri", "cancel", "next-proof"])
def test_alias_body_read_once_without_ref_or_permission_reuse(
    tmp_path: Path, fault: str
) -> None:
    store = FileEvidenceStore(tmp_path)
    raw = b'{"value":1}'
    first = store.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="body/1",
            visibility="private",
            producer="first-producer",
        ),
    )
    alias = store.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="body/1",
            visibility="public",
            producer="second-producer",
        ),
    )
    assert first != alias and first.sha256 == alias.sha256
    proof = ReadOnlyEvidence(tmp_path, max_object_bytes=1024, reuse_within_proof=True)
    assert proof.read(first, guard()) == raw
    if fault == "size":
        with pytest.raises(EvidenceIntegrityError):
            proof.read(
                alias.model_copy(update={"size_bytes": alias.size_bytes + 1}), guard()
            )
    elif fault == "uri":
        with pytest.raises((ValueError, EvidenceIntegrityError)):
            proof.read(
                alias.model_copy(update={"uri": "cas://sha256/" + "0" * 64}), guard()
            )
    elif fault == "cancel":

        class Cancel:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "original-proof-read")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        with pytest.raises(OperationStopped):
            proof.read(alias, Cancel())
    elif fault == "next-proof":
        assert proof.read(alias, guard()) == raw
        (tmp_path / "blobs" / first.sha256).write_bytes(b"changed")
        fresh = ReadOnlyEvidence(
            tmp_path, max_object_bytes=1024, reuse_within_proof=True
        )
        with pytest.raises(EvidenceIntegrityError):
            fresh.read(alias, guard())
    else:
        assert proof.read(alias, guard()) == raw
        assert proof.read_count == 2
    assert proof.body_read_count == len(proof.unique_objects) == 1
