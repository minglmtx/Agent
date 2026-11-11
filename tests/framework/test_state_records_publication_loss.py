"""A lost CAS ack retains a candidate, never a false confirmed state fact."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.ports.lifecycle import OperationControl
from state_storage_fixtures import fixture


@pytest.mark.parametrize("kind", ["baseline", "reset"])
@pytest.mark.parametrize("committed", [False, True])
def test_state_candidate_survives_original_publication_error_without_claiming_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, committed: bool
) -> None:
    data = fixture(tmp_path)
    receipt = data.candidate(kind)
    original = data.store.put
    error = TimeoutError("Synthetic original state CAS acknowledgement lost")
    candidates: list[EvidenceRef] = []

    def lose(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        candidates.append(evidence_reference(raw, metadata))
        if committed:
            assert original(raw, metadata, control) == candidates[-1]
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(data.store, "put", lose)
        with pytest.raises(TimeoutError) as caught:
            data.publish(receipt, receipt.operation)
    assert caught.value is error and len(candidates) == 1
    assert getattr(error, "state_candidate_reference") == candidates[0]
    assert not hasattr(error, "reference")
    path = tmp_path / "blobs" / candidates[0].sha256
    assert path.exists() == committed
    if committed:
        assert path.read_bytes() == receipt.model_dump_json().encode()
