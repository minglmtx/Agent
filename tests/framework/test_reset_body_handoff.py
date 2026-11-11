"""Exact Reset producer bodies, current authority and original failure boundaries."""

from collections import Counter
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.adapters.sites.task_finalization_authorities import (
    FinalizationResetAuthority,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.reset_publication import reset_documents
from lab_generate_skill.domain.state_scope import StateCommitUnconfirmed
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from state_storage_fixtures import fixture
from test_lifecycle import ManualClock
from task_capture_port_fixtures import capture_case
from task_finalization_port_fixtures import bind_finalization
from site_instance_fixtures import node_path as node_path


def test_producer_bodies_publication_and_same_call_consumption_use_fresh_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = fixture(tmp_path)
    reads: Counter[EvidenceRef] = Counter()
    original = c.store.read

    def read(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        reads[reference] += 1
        return original(reference, control=control)

    monkeypatch.setattr(c.store, "read", read)
    publication = c.adapter.publish_reset_inputs(
        c.reset, c.reset_inputs, c.reset.operation
    )
    assert not set(reads).intersection(r for r, _ in reset_documents(c.reset_inputs))
    assert reads[publication.reference] == 1 and reads[c.protected_ref] == 1
    before = reads.copy()
    assert c.adapter.load_reset_publication(publication, c.reset.operation) == c.reset
    assert reads == before and c.authority.calls == ["reset"] * 3
    # A later ordinary independent review still reads its full original graph.
    assert c.adapter.load_reset(publication.reference, c.reset.operation) == c.reset
    assert sum(reads.values()) > sum(before.values())


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_producer_handoff_keeps_full_transitive_dependency_verification(
    tmp_path: Path, fault: str
) -> None:
    c = fixture(tmp_path)
    path = tmp_path / "blobs" / c.protected_ref.sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt complete dependency")
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(
        EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    ):
        c.adapter.publish_reset_inputs(c.reset, c.reset_inputs, c.reset.operation)
    assert set((tmp_path / "blobs").iterdir()) == before and not c.authority.calls


@pytest.mark.parametrize("fault", ["body", "scope", "reference"])
def test_changed_producer_body_is_refused_before_authority_or_write(
    tmp_path: Path, fault: str
) -> None:
    c = fixture(tmp_path)
    inputs = c.reset_inputs
    if fault == "body":
        inputs = inputs.model_copy(
            update={"spec": inputs.spec.model_copy(update={"spec_id": "changed"})}
        )
    elif fault == "scope":
        inputs = inputs.model_copy(
            update={
                "plan": inputs.plan.model_copy(
                    update={
                        "scope": inputs.plan.scope.model_copy(
                            update={"context_id": "foreign"}
                        )
                    }
                )
            }
        )
    else:
        inputs = inputs.model_copy(
            update={
                "health_ref": inputs.health_ref.model_copy(
                    update={"sha256": "f" * 64, "uri": "cas://sha256/" + "f" * 64}
                )
            }
        )
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError, ValueError)):
        c.adapter.publish_reset_inputs(c.reset, inputs, c.reset.operation)
    assert set((tmp_path / "blobs").iterdir()) == before and not c.authority.calls


@pytest.mark.parametrize(
    "fault", ["foreign-adapter", "issuer", "producer", "scope", "revoked", "expired"]
)
def test_handoff_is_same_publication_and_never_reuses_permission(
    tmp_path: Path, fault: str
) -> None:
    c = fixture(tmp_path)
    clock = ManualClock()
    clock.wall = c.reset.operation.deadline - timedelta(seconds=60)
    c.adapter.controls = OperationGuards(clock, c.switch)
    publication = c.adapter.publish_reset_inputs(
        c.reset, c.reset_inputs, c.reset.operation
    )
    adapter = c.adapter
    operation = c.reset.operation
    if fault == "foreign-adapter":
        adapter = EvidenceStateRecords(c.store, c.adapter.controls, c.authority)
    elif fault == "issuer":
        publication = replace(publication, issuer=object())
    elif fault == "producer":
        publication = replace(
            publication,
            reference=publication.reference.model_copy(
                update={"producer": "foreign-producer"}
            ),
        )
    elif fault == "scope":
        operation = operation.model_copy(update={"owner_id": "foreign-owner"})
    elif fault == "revoked":
        c.authority.denied = True
    else:
        clock.sleep(61)
    with pytest.raises(OperationStopped if fault == "expired" else OwnershipConflict):
        adapter.load_reset_publication(publication, operation)


@pytest.mark.parametrize("fault", ["readback", "revoked-after-write"])
def test_failed_readback_retains_reference_without_usable_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = fixture(tmp_path)
    read = c.store.read
    verify = c.authority.verify_reset

    def failing_read(
        reference: EvidenceRef, control: OperationControl | None = None
    ) -> bytes:
        if reference.content_schema == "reset-receipt/1" and fault == "readback":
            raise OSError("synthetic exact readback failure")
        return read(reference, control=control)

    def verify_current(*args: Any) -> None:
        if fault == "revoked-after-write" and len(c.authority.calls) == 1:
            c.authority.denied = True
        verify(*args)

    monkeypatch.setattr(c.store, "read", failing_read)
    monkeypatch.setattr(c.authority, "verify_reset", verify_current)
    with pytest.raises(StateCommitUnconfirmed) as caught:
        c.adapter.publish_reset_inputs(c.reset, c.reset_inputs, c.reset.operation)
    assert read(caught.value.reference) == c.reset.model_dump_json().encode()


def test_real_finalization_transmits_producer_bodies_and_loads_without_restore_replay(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        case.initial.start()
        f = bind_finalization(case)
        closed = f.close()
        assert isinstance(f.finalizer.states, EvidenceStateRecords)
        state_authority = f.finalizer.states.authority
        assert isinstance(state_authority, FinalizationResetAuthority)
        native_reset = state_authority.checks.reset
        native_calls = []

        def measure_native(*args: Any, **kwargs: Any) -> Any:
            native_calls.append(True)
            return native_reset(*args, **kwargs)

        monkeypatch.setattr(state_authority.checks, "reset", measure_native)
        f.restore()
        state = f.finalizer.state
        assert state.reset_publication is not None and state.reset_ref is not None
        assert len(native_calls) == 1
        refs = len(state.references)
        requests = len(case.initial.preparation.requests)
        resumes = f.resume.calls
        assert isinstance(f.finalizer.states, EvidenceStateRecords)

        def no_graph(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("same-call Reset graph was read again")

        monkeypatch.setattr(f.finalizer.states, "load_reset", no_graph)
        monkeypatch.setattr(f.finalizer.states.resets, "verify", no_graph)
        operation = f.operation("retained-consumption")
        receipt = f.finalizer.load_restored_reset(
            state.reset_ref,
            operation,
            case.initial.preparation.original.resource.controls.bind(operation),
        )
        assert receipt == state.reset and len(state.references) == refs
        assert len(native_calls) == 1
        assert (
            len(case.initial.preparation.requests) == requests
            and f.resume.calls == resumes
        )
        assert state.reset_inputs is not None and state.reset is not None
        state_authority.verify_reset(state.reset_inputs, state.reset, operation)
        assert len(native_calls) == 2


@pytest.mark.parametrize(
    "fault",
    ["source-denied", "expired", "scope", "reference", "phase", "producer-inputs"],
)
def test_native_finalization_handoff_keeps_current_authority_and_original_scope(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        case.initial.start()
        f = bind_finalization(case)
        f.close()
        f.restore()
        state = f.finalizer.state
        assert state.reset_ref is not None and state.reset_inputs is not None
        operation = f.operation("consume-after-fault")
        reference = state.reset_ref
        if fault == "source-denied":
            f.authority.denied = True
        elif fault == "expired":
            operation = operation.model_copy(
                update={"deadline": operation.deadline - timedelta(days=1)}
            )
        elif fault == "scope":
            operation = operation.model_copy(update={"owner_id": "foreign-owner"})
        elif fault == "reference":
            reference = reference.model_copy(update={"producer": "foreign-producer"})
        elif fault == "phase":
            state.phase = "quarantined"
        else:
            state.reset_inputs = state.reset_inputs.model_copy(
                update={
                    "plan_ref": state.reset_inputs.plan_ref.model_copy(
                        update={"producer": "foreign-producer"}
                    )
                }
            )
        before = (len(case.initial.preparation.requests), f.resume.calls)
        try:
            with pytest.raises(
                PermissionError
                if fault == "source-denied"
                else OperationStopped if fault == "expired" else OwnershipConflict
            ):
                f.finalizer.load_restored_reset(
                    reference,
                    operation,
                    case.initial.preparation.original.resource.controls.bind(operation),
                )
            assert (len(case.initial.preparation.requests), f.resume.calls) == before
        finally:
            f.authority.denied = False
