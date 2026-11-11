"""Real producer/body/StateRecords joins, with explicit unit-only authority."""

from pathlib import Path
from typing import Any
import pytest

from lab_generate_skill.adapters.plans.baseline_read import baseline_input_bodies
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.domain.baseline_read import (
    BaselineReadRequest,
    BaselineReadBodies,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    OperationStopped,
    EvidenceNotFound,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import StateCommitUnconfirmed
from lab_generate_skill.ports.lifecycle import OperationControl
from state_storage_fixtures import fixture


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "request",
        "revoked",
        "cancel",
        "missing",
        "body",
        "verified",
        "wrong_type",
    ],
)
def test_complete_graph_handoff_publish_readback_and_live_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c = fixture(tmp_path)
    requests: list[BaselineReadRequest] = []
    physical: list[tuple[int, int]] = []
    parent_reads: list[EvidenceRef] = []

    class Inputs:
        def load_baseline_inputs(
            self, request: BaselineReadRequest, control: OperationControl
        ) -> BaselineReadBodies:
            requests.append(request)
            if fault == "cancel":
                raise OperationStopped("CANCELLED", request.operation.operation_id)
            evidence = ReadOnlyEvidence(
                tmp_path, max_object_bytes=64 * 1024**2, reuse_within_proof=True
            )
            result = baseline_input_bodies(request, evidence, control)
            physical.append((evidence.body_read_count, len(evidence.unique_objects)))
            if fault == "revoked":
                c.authority.denied = True
            if fault == "request":
                result = result.model_copy(
                    update={
                        "request": request.model_copy(
                            update={
                                "operation": request.operation.model_copy(
                                    update={"operation_id": "foreign"}
                                )
                            }
                        )
                    }
                )
            if fault in ("body", "verified", "wrong_type"):
                wrong: Any = result.model_dump()
                if fault == "body":
                    wrong["bodies"][0]["json_text"] = "{}"
                elif fault == "verified":
                    wrong["verified"] = []
                else:
                    wrong["inputs"] = []
                return BaselineReadBodies.model_validate(wrong)
            return result

    adapter = EvidenceStateRecords(
        c.store, c.adapter.controls, c.authority, input_reads=Inputs()
    )
    if fault == "missing":
        (tmp_path / "blobs" / c.protected_ref.sha256).unlink()
    original = c.store.read

    def read(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        parent_reads.append(reference)
        return original(reference, control=control)

    monkeypatch.setattr(c.store, "read", read)
    before = set((tmp_path / "blobs").iterdir())
    if fault == "none":
        ref = adapter.publish_baseline_verified(c.baseline, c.baseline.operation)
        assert parent_reads == [ref] and len(requests) == 1
        assert c.authority.calls == ["baseline", "baseline"]
        assert adapter.load_baseline(ref, c.baseline.operation) == c.baseline
        assert len(requests) == 2 and all(total == unique for total, unique in physical)
        assert c.authority.calls == ["baseline"] * 3
        c.authority.denied = True
        with pytest.raises(OwnershipConflict):
            adapter.load_baseline(ref, c.baseline.operation)
        assert len(requests) == 3
    else:
        with pytest.raises(
            (ValueError, OwnershipConflict, OperationStopped, EvidenceNotFound)
        ):
            adapter.publish_baseline_verified(c.baseline, c.baseline.operation)
        assert len(requests) == 1
        assert set((tmp_path / "blobs").iterdir()) == before and parent_reads == []


@pytest.mark.parametrize("fault", ["readback", "authority"])
def test_readback_failure_retains_exact_published_reference_and_first_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c = fixture(tmp_path)
    first = OSError("original baseline readback failed")
    original_read = c.store.read
    original_verify = c.authority.verify_baseline

    def read(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        if reference.content_schema == "baseline-receipt/1":
            raise first
        return original_read(reference, control=control)

    def verify(*args: Any) -> None:
        if len(c.authority.calls) == 1 and fault == "authority":
            c.authority.denied = True
        original_verify(*args)

    monkeypatch.setattr(c.store, "read", read if fault == "readback" else original_read)
    monkeypatch.setattr(c.authority, "verify_baseline", verify)
    with pytest.raises(StateCommitUnconfirmed) as caught:
        c.adapter.publish_baseline_verified(c.baseline, c.baseline.operation)
    assert (
        original_read(caught.value.reference) == c.baseline.model_dump_json().encode()
    )
    assert (
        caught.value.__cause__ is first
        if fault == "readback"
        else isinstance(caught.value.__cause__, OwnershipConflict)
    )
