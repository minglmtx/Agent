"""Actual CAS trace consumption, source validation and commit/failure boundaries."""

from lab_generate_skill.ports.lifecycle import OperationControl

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.clock import SystemClock
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.trace import InteractionTrace, TraceCommitUnconfirmed
from lab_generate_skill.runtime.lifecycle import OperationGuards
from retrieval_fixtures import reference
from test_run_journal import command, CancelSwitch
from trace_fixtures import fixture, TraceFixture, UnitTraceAuthority


def setup(
    root: Path, outcomes: tuple[str, ...] = ("invalid", "returned", "returned")
) -> tuple[FileEvidenceStore, EvidenceTraceRecords, UnitTraceAuthority, TraceFixture]:
    store = FileEvidenceStore(root)
    authority = UnitTraceAuthority(store)
    adapter = EvidenceTraceRecords(
        store, OperationGuards(SystemClock(), CancelSwitch()), authority
    )
    return store, adapter, authority, fixture(store, outcomes)


def replace_after(
    data: TraceFixture, store: FileEvidenceStore, changes: dict[str, object]
) -> InteractionTrace:
    trace = data.trace
    turn = trace.turns[-1]
    event = turn.interaction
    assert event and event.result
    observed = data.observations[-1].model_copy(update=changes)
    ref = reference(observed, "observation/1", "public", store)
    result = event.result.model_copy(
        update={
            "observation_ref": ref,
            "return_ref": reference(
                {
                    "action_id": event.action.action_id,
                    "observation_ref": ref.model_dump(mode="json"),
                    "terminal": event.result.terminal,
                },
                "browser-step-return/1",
                store=store,
            ),
        }
    )
    return trace.model_copy(
        update={
            "turns": (
                *trace.turns[:-1],
                turn.model_copy(
                    update={"interaction": event.model_copy(update={"result": result})}
                ),
            )
        }
    )


def test_actual_cas_repeat_and_load_preserve_original_counts_and_bytes(
    tmp_path: Path,
) -> None:
    store, adapter, authority, data = setup(tmp_path)
    trace = data.trace
    ref = adapter.publish(trace, trace.operation)
    assert adapter.publish(trace, trace.operation) == ref
    assert adapter.load(ref, command()) == trace
    assert adapter.load(ref, command(attempt="attempt")) == trace
    assert store.read(ref) == trace.model_dump_json().encode()
    assert authority.calls == 4


@pytest.mark.parametrize(
    "outcome",
    [
        "not_dispatched",
        "uncertain",
        "failed",
        "generation_unknown",
        "unprocessed",
        "invalid",
    ],
)
def test_nonreturn_diagnostics_can_be_preserved_without_execution_permission(
    tmp_path: Path, outcome: str
) -> None:
    store, adapter, authority, data = setup(tmp_path, (outcome,))
    ref = adapter.publish(data.trace, data.trace.operation)
    result = adapter.load(ref, command())
    assert result.interactions == 0 and result.generations == 1
    assert result.stop_reason == data.trace.stop_reason


def test_return_without_saved_observation_is_preserved_as_incomplete(
    tmp_path: Path,
) -> None:
    store, adapter, authority, data = setup(tmp_path, ("returned_incomplete",))
    ref = adapter.publish(data.trace, data.trace.operation)
    result = adapter.load(ref, command())
    assert result.interactions == 1 and result.stop_reason == "error"


@pytest.mark.parametrize(
    "item",
    ["initial", "input", "parameters", "response", "parse_failure", "return", "stop"],
)
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_deep_raw_evidence_required_on_producer_and_consumer(
    tmp_path: Path, item: str, fault: str
) -> None:
    store, adapter, authority, data = setup(tmp_path)
    trace = data.trace
    first = trace.turns[0]
    last = trace.turns[-1]
    assert (
        first.decision and first.decision.failure_ref and first.generation.response_ref
    )
    assert last.interaction and last.interaction.result
    ref = adapter.publish(trace, trace.operation)
    targets = {
        "initial": trace.initial_observation_ref,
        "input": first.generation.input_ref,
        "parameters": first.generation.parameters_ref,
        "response": first.generation.response_ref,
        "parse_failure": first.decision.failure_ref,
        "return": last.interaction.result.return_ref,
        "stop": trace.stop_evidence_ref,
    }
    path = tmp_path / "blobs" / targets[item].sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"damaged")
    before = set((tmp_path / "blobs").iterdir())
    for call in (
        lambda: adapter.publish(trace, trace.operation),
        lambda: adapter.load(ref, command()),
    ):
        with pytest.raises(
            EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
        ):
            call()
    assert set((tmp_path / "blobs").iterdir()) == before and authority.calls == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": 7},
        {"context_id": "other"},
        {"attempt_id": "other"},
        {"observation_id": "initial-observation"},
    ],
)
def test_actual_observations_cannot_skip_or_change_identity(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    store, adapter, authority, data = setup(tmp_path, ("returned",))
    trace = replace_after(data, store, changes)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OwnershipConflict, match="contiguous sequences"):
        adapter.publish(trace, trace.operation)
    assert set((tmp_path / "blobs").iterdir()) == before and authority.calls == 0


def test_error_observation_is_still_a_return_not_task_failure(tmp_path: Path) -> None:
    store, adapter, authority, data = setup(tmp_path, ("returned",))
    trace = replace_after(
        data,
        store,
        {
            "state": "error",
            "error_code": "browser-error",
            "last_action_error": "click rejected",
        },
    )
    ref = adapter.publish(trace, trace.operation)
    result = adapter.load(ref, command())
    assert result.interactions == 1 and not hasattr(result, "evaluation")


def test_authority_rejects_forged_well_formed_raw_return(tmp_path: Path) -> None:
    store, adapter, authority, data = setup(tmp_path, ("returned",))
    turn = data.trace.turns[0]
    event = turn.interaction
    assert event and event.result
    wrong = reference({"unverified": True}, "browser-step-return/1", store=store)
    bad = turn.model_copy(
        update={
            "interaction": event.model_copy(
                update={"result": event.result.model_copy(update={"return_ref": wrong})}
            )
        }
    )
    trace = data.trace.model_copy(update={"turns": (bad,)})
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OwnershipConflict, match="actual browser return"):
        adapter.publish(trace, trace.operation)
    assert set((tmp_path / "blobs").iterdir()) == before


def test_permission_denial_and_foreign_scope_reject_without_publication(
    tmp_path: Path,
) -> None:
    store, adapter, authority, data = setup(tmp_path)
    trace = data.trace
    ref = adapter.publish(trace, trace.operation)
    before = set((tmp_path / "blobs").iterdir())
    for changes in (
        {"run_id": "other"},
        {"owner_id": "other"},
        {"attempt_id": "other"},
    ):
        with pytest.raises(OwnershipConflict):
            adapter.load(ref, command().model_copy(update=changes))
    authority.denied = True
    with pytest.raises(OwnershipConflict, match="authority denied"):
        adapter.publish(trace, trace.operation)
    with pytest.raises(OwnershipConflict, match="authority denied"):
        adapter.load(ref, command())
    assert set((tmp_path / "blobs").iterdir()) == before


def test_old_operation_can_be_saved_with_independent_scoped_cleanup(
    tmp_path: Path,
) -> None:
    store, adapter, authority, data = setup(tmp_path)
    old = data.trace.operation.model_copy(
        update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    trace = data.trace.model_copy(update={"operation": old})
    with pytest.raises(OperationStopped):
        adapter.publish(trace, old)
    cleanup = command("late-save", attempt="attempt", cleanup_parent=old.operation_id)
    ref = adapter.publish(trace, cleanup)
    assert adapter.load(ref, command()).operation == old
    for changes in (
        {"parent_operation_id": "other"},
        {"attempt_id": "other"},
        {"allocation_id": "new"},
    ):
        with pytest.raises(OwnershipConflict):
            adapter.publish(trace, cleanup.model_copy(update=changes))


def test_put_failure_retains_complete_exception_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, adapter, authority, data = setup(tmp_path)
    primary = OSError("write failed")
    cleanup = OSError("close failed")
    error = ExceptionGroup("both", [primary, cleanup])

    def fail(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        raise error

    monkeypatch.setattr(store, "put", fail)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(ExceptionGroup) as raised:
        adapter.publish(data.trace, data.trace.operation)
    assert raised.value is error and raised.value.exceptions == (primary, cleanup)
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("when", ["authority", "after_put"])
def test_cancellation_preserves_known_reference_only_after_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    store, adapter, authority, data = setup(tmp_path)
    switch = CancelSwitch()
    adapter.controls = OperationGuards(SystemClock(), switch)
    op = data.trace.operation.model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="cancel", run_id="run", owner_id="owner"
            )
        }
    )
    trace = data.trace.model_copy(update={"operation": op})
    original_put = store.put

    def cancel() -> None:
        switch.cancelled = True

    def put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        ref = original_put(raw, metadata)
        cancel()
        return ref

    if when == "authority":
        authority.callback = cancel
    else:
        monkeypatch.setattr(store, "put", put)
    before = set((tmp_path / "blobs").iterdir())
    if when == "authority":
        with pytest.raises(OperationStopped):
            adapter.publish(trace, op)
        assert set((tmp_path / "blobs").iterdir()) == before
    else:
        with pytest.raises(TraceCommitUnconfirmed) as raised:
            adapter.publish(trace, op)
        assert isinstance(raised.value.__cause__, OperationStopped)
        assert store.read(raised.value.reference) == trace.model_dump_json().encode()
        assert len(set((tmp_path / "blobs").iterdir()) - before) == 1
        assert (
            adapter.load(
                raised.value.reference,
                command("inspect", attempt="attempt", cleanup_parent=op.operation_id),
            )
            == trace
        )


def test_wrong_schema_visibility_and_root_type_are_rejected(tmp_path: Path) -> None:
    store, adapter, authority, data = setup(tmp_path)
    ref = adapter.publish(data.trace, data.trace.operation)
    for change in ({"visibility": "public"}, {"content_schema": "interaction-trace/0"}):
        with pytest.raises(ValueError):
            adapter.load(ref.model_copy(update=change), command())
    invalid: tuple[object, ...] = (None, [], {}, 42)
    validate: Callable[[object], InteractionTrace] = InteractionTrace.model_validate
    for value in invalid:
        with pytest.raises(ValidationError):
            validate(value)


def test_trace_object_limit_rejects_without_losing_original_facts(
    tmp_path: Path,
) -> None:
    store, adapter, authority, data = setup(tmp_path)
    before = {p.name: p.read_bytes() for p in (tmp_path / "blobs").iterdir()}
    limit = max(map(len, before.values())) + 1
    assert len(data.trace.model_dump_json().encode()) > limit
    limited = FileEvidenceStore(tmp_path, max_object_bytes=limit)
    bounded = EvidenceTraceRecords(limited, adapter.controls, authority)
    with pytest.raises(EvidenceIntegrityError, match="object limit"):
        bounded.publish(data.trace, data.trace.operation)
    assert {p.name: p.read_bytes() for p in (tmp_path / "blobs").iterdir()} == before
