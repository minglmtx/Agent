"""Real preparation constructors retain semantic/current authority after body handoff."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.domain.preparation_read import (
    PreparationReadRequest,
    PreparationReadBodies,
)
from lab_generate_skill.domain.preparation_record import PreparationRecordFailure
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from preparation_record_fixtures import fixture


@pytest.mark.parametrize(
    "fault", ["none", "revoked", "request", "cancelled", "missing"]
)
def test_fresh_preparation_proof_keeps_original_checks_authority_and_failure_exit(
    tmp_path: Path, fault: str
) -> None:
    c = fixture(tmp_path)
    reads: list[PreparationReadRequest] = []

    class Inputs:
        def load_preparation_inputs(
            self, request: PreparationReadRequest, control: OperationControl
        ) -> PreparationReadBodies:
            control.checkpoint()
            reads.append(request)
            if fault == "cancelled":
                raise PermissionError("Unit preparation read cancelled")
            loaded = c.adapter.reader.load_with_bodies(
                request.selection, request.operation, control
            )
            assert loaded.private_spec is not None and loaded.snapshot is not None
            selected = request
            if fault == "request":
                selected = request.model_copy(
                    update={
                        "operation": request.operation.model_copy(
                            update={"operation_id": "foreign"}
                        )
                    }
                )
            result = PreparationReadBodies(
                request=selected,
                inputs=loaded.inputs,
                verified=tuple(loaded.verified),
                private_spec_json=loaded.private_spec.decode(),
                snapshot_json=loaded.snapshot.decode(),
            )
            if fault == "revoked":
                c.authority.denied = True
            return result

    adapter = EvidencePreparationRecords(
        c.store,
        c.adapter.controls,
        c.adapter.reader.bindings,
        c.adapter.checks,
        c.authority,
        input_reads=Inputs(),
    )
    if fault == "missing":
        (tmp_path / "evidence/blobs" / c.selection.request_ref.sha256).unlink()
    before = set((tmp_path / "evidence/blobs").iterdir())
    if fault == "none":
        publication = adapter.publish(c.selection, c.request.operation)
        prepared = adapter.load(publication, c.request.operation)
        assert prepared.public_task.identity == c.request.task
        assert len(reads) == 2 and c.authority.calls == 2
        c.authority.denied = True
        with pytest.raises(PermissionError, match="binding denied"):
            adapter.load(publication, c.request.operation)
        assert len(reads) == 3
    else:
        with pytest.raises(PreparationRecordFailure) as caught:
            adapter.publish(c.selection, c.request.operation)
        assert caught.value.phase == "verify" and caught.value.references == ()
        assert set((tmp_path / "evidence/blobs").iterdir()) == before
        assert len(reads) == 1
        if fault == "request":
            assert isinstance(caught.value.__cause__, OwnershipConflict)
        if fault == "revoked":
            assert isinstance(caught.value.__cause__, PermissionError)
            assert c.authority.calls == 1
