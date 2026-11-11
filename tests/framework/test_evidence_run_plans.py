"""Actual CAS plan roundtrip and run-journal consumer, with explicit fixtures.

Fixture input documents are not production release/authorization attestations.
This checks transport, identities, capacity and failure effects, not admission.
"""

from lab_generate_skill.ports.lifecycle import OperationControl

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.execution import RunBinding, RunEvent
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.runtime.lifecycle import OperationGuards

from test_run_journal import CancelSwitch, command
from test_run_plan import binding, plan


def persisted_plan(store: FileEvidenceStore) -> RunPlan:
    def materialize(value: object) -> object:
        if isinstance(value, dict):
            if value.get("schema_version") == "evidence-ref/1":
                ref = EvidenceRef.model_validate(value)
                data = json.dumps(
                    {
                        "unit_fixture": True,
                        "schema": ref.content_schema,
                        "visibility": ref.visibility,
                    },
                    sort_keys=True,
                ).encode()
                return store.put(
                    data,
                    EvidenceMetadata(
                        media_type=ref.media_type,
                        content_schema=ref.content_schema,
                        visibility=ref.visibility,
                        producer="unit-plan-fixture",
                    ),
                ).model_dump(mode="json")
            return {k: materialize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [materialize(v) for v in value]
        return value

    return RunPlan.model_validate_json(
        json.dumps(materialize(plan().model_dump(mode="json")))
    )


def loader(store: FileEvidenceStore) -> RunPlans:
    return EvidenceRunPlans(store, OperationGuards(SystemClock(), CancelSwitch()))


def frozen_binding(store: FileEvidenceStore, value: RunPlan) -> RunBinding:
    ref = loader(store).publish(value, command())
    return RunBinding.model_validate(
        binding(value).model_copy(update={"plan_ref": ref})
    )


def test_producer_consumer_and_real_run_journal_share_exact_capacity(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    journal_root = tmp_path / "run"
    journal_root.mkdir()
    store = FileEvidenceStore(evidence)
    value = persisted_plan(store)
    original = frozen_binding(store, value)
    plans = loader(store)
    assert plans.publish(value, command()) == original.plan_ref
    loaded = plans.load(original, command())
    assert loaded == value
    journal = FileRunJournal(
        journal_root,
        original,
        OperationGuards(SystemClock(), CancelSwitch()),
        store,
        capacity=loaded.run_capacity,
    )
    op = command("planned")
    event = RunEvent(
        stage="planned",
        operation=op,
        occurred_at=datetime.now(timezone.utc),
        component_id="unit-plan-consumer",
    )
    snapshot = journal.create(event, op)
    assert snapshot.capacity == value.run_capacity
    assert snapshot.binding == original
    assert journal.create(event, op) == snapshot
    assert plans.load(original, command()) == value


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": "other"},
        {"attempt_id": "attempt"},
        {"mode": "cleanup", "parent_operation_id": "parent"},
    ],
)
def test_publish_rejects_wrong_operation_before_write(
    tmp_path: Path, change: dict[str, object]
) -> None:
    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    before = set(tmp_path.rglob("*"))
    op = OperationContext.model_validate(command().model_copy(update=change))
    with pytest.raises(OwnershipConflict):
        loader(store).publish(value, op)
    assert set(tmp_path.rglob("*")) == before


@pytest.mark.parametrize(
    "change", [{"run_id": "other"}, {"owner_id": "other"}, {"attempt_id": "attempt"}]
)
def test_load_rejects_wrong_operation(
    tmp_path: Path, change: dict[str, object]
) -> None:
    store = FileEvidenceStore(tmp_path)
    original = frozen_binding(store, persisted_plan(store))
    op = OperationContext.model_validate(command().model_copy(update=change))
    with pytest.raises(OwnershipConflict):
        loader(store).load(original, op)


def test_load_allows_bounded_cleanup_read(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    original = frozen_binding(store, value)
    assert loader(store).load(original, command(cleanup_parent="prior")) == value


def test_missing_direct_input_blocks_publish_and_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    original = frozen_binding(store, value)
    target = value.resources.configuration_ref
    read = store.read

    def missing(ref: EvidenceRef, control: OperationControl | None = None) -> bytes:
        if ref == target:
            raise EvidenceNotFound("fixture input disappeared")
        return read(ref)

    monkeypatch.setattr(store, "read", missing)
    before = set(tmp_path.rglob("*"))
    with pytest.raises(EvidenceNotFound):
        loader(store).publish(value, command())
    with pytest.raises(EvidenceNotFound):
        loader(store).load(original, command())
    assert set(tmp_path.rglob("*")) == before


def test_publish_commit_lost_ack_can_reconcile_same_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    put = store.put
    committed: list[EvidenceRef] = []

    def lose_ack(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        committed.append(put(data, metadata))
        raise OSError("lost plan acknowledgement")

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "put", lose_ack)
        with pytest.raises(OSError, match="lost plan acknowledgement"):
            loader(store).publish(value, command())
    assert len(committed) == 1
    assert loader(store).publish(value, command()) == committed[0]
    assert RunPlan.model_validate_json(store.read(committed[0])) == value


def test_revalidation_rejects_trusted_escape_hatch_before_effect(
    tmp_path: Path,
) -> None:
    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    broken = value.model_copy(update={"tasks": ()})
    before = set(tmp_path.rglob("*"))
    with pytest.raises(ValidationError):
        loader(store).publish(broken, command())
    assert set(tmp_path.rglob("*")) == before


def test_expired_operation_and_wrong_payload(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    original = frozen_binding(store, value)
    expired = OperationContext.model_validate(
        command().model_copy(
            update={"deadline": datetime(2000, 1, 1, tzinfo=timezone.utc)}
        )
    )
    with pytest.raises(OperationStopped):
        loader(store).publish(value, expired)
    with pytest.raises(OperationStopped):
        loader(store).load(original, expired)
    malformed = store.put(
        b"{}",
        EvidenceMetadata(
            media_type="application/json",
            content_schema="run-plan/3",
            visibility="private",
            producer="unit-fixture",
        ),
    )
    changed = RunBinding.model_validate(
        original.model_copy(update={"plan_ref": malformed})
    )
    with pytest.raises(ValidationError):
        loader(store).load(changed, command())


def test_wrong_release_and_plan_visibility_are_not_fallbacks(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    original = frozen_binding(store, value)
    for fields in (
        {"release_ref": value.task_manifest_ref},
        {"plan_ref": value.task_manifest_ref},
        {"plan_ref": original.plan_ref.model_copy(update={"visibility": "public"})},
    ):
        changed = RunBinding.model_validate(original.model_copy(update=fields))
        with pytest.raises(ValueError):
            loader(store).load(changed, command())


def test_cancellation_between_reads_prevents_plan_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    cancellation = CancelSwitch()
    plans = EvidenceRunPlans(store, OperationGuards(SystemClock(), cancellation))
    op = OperationContext.model_validate(
        command().model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="stop", run_id="run", owner_id="owner"
                )
            }
        )
    )
    original = store.read
    before = set(tmp_path.rglob("*"))

    def cancel_after_read(
        reference: EvidenceRef, control: OperationControl | None = None
    ) -> bytes:
        raw = original(reference)
        cancellation.cancelled = True
        return raw

    monkeypatch.setattr(store, "read", cancel_after_read)
    with pytest.raises(OperationStopped):
        plans.publish(value, op)
    assert set(tmp_path.rglob("*")) == before


def test_injected_input_checker_runs_each_time_and_never_skips_missing_input(
    tmp_path: Path,
) -> None:
    from lab_generate_skill.adapters.plans.evidence import check_run_plan_input_evidence

    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    calls: list[tuple[RunPlan, OperationContext]] = []

    class ExactInputs:
        def verify_inputs(
            self, plan: RunPlan, op: OperationContext, control: OperationControl
        ) -> None:
            calls.append((plan, op))
            check_run_plan_input_evidence(plan, store, control)

    plans = EvidenceRunPlans(
        store,
        OperationGuards(SystemClock(), CancelSwitch()),
        input_checks=ExactInputs(),
    )
    published = plans.publish(value, command())
    original = RunBinding.model_validate(
        binding(value).model_copy(update={"plan_ref": published})
    )
    assert plans.load(original, command()) == value
    assert plans.load(original, command()) == value
    assert len(calls) == 3
    ref = value.split_manifest_ref
    (tmp_path / "blobs" / ref.sha256).unlink()
    with pytest.raises(EvidenceNotFound):
        plans.load(original, command())
    assert len(calls) == 4
