"""Producer/consumer agreement using actual immutable files and unit authority."""

from lab_generate_skill.ports.lifecycle import OperationControl

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.bank import BankManifest
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext, CancellationRef
from lab_generate_skill.domain.retrieval import RetrievalResult, ScoringReceipt
from lab_generate_skill.domain.retrieval_execution import RetrievalExecution
from lab_generate_skill.runtime.lifecycle import OperationGuards

from retrieval_fixtures import fixture, reference, RetrievalFixture
from test_construction_state import skill
from test_run_journal import command, CancelSwitch


class UnitAuthority:
    def __init__(self, store: FileEvidenceStore) -> None:
        self.store = store
        self.denied = False

    def verify(
        self,
        result: RetrievalResult,
        bank: BankManifest,
        split: SplitManifest,
        op: OperationContext,
    ) -> None:
        if self.denied or (op.run_id, op.owner_id) != ("run", "owner"):
            raise OwnershipConflict("Unit qualification rejected")
        receipt = ScoringReceipt.model_validate_json(
            self.store.read(result.score_evidence_ref)
        )
        execution = RetrievalExecution.model_validate_json(
            self.store.read(receipt.execution_ref)
        )
        if execution.query != result.query or execution.scope != result.scope:
            raise OwnershipConflict("Unit execution rejected")
        for record in bank.records:
            for source in record.sources:
                if json.loads(self.store.read(source.review_ref)) != {"reviewed": True}:
                    raise OwnershipConflict("Unit review rejected")


def setup(
    root: Path,
) -> tuple[
    FileEvidenceStore, RetrievalFixture, UnitAuthority, EvidenceRetrievalRecords
]:
    store = FileEvidenceStore(root)
    data = fixture(store)
    authority = UnitAuthority(store)
    adapter = EvidenceRetrievalRecords(
        store, OperationGuards(SystemClock(), CancelSwitch()), authority
    )
    return store, data, authority, adapter


def test_publish_repeat_load_to_generation_input(tmp_path: Path) -> None:
    store, data, authority, adapter = setup(tmp_path)
    first = adapter.publish(data.result, command())
    assert adapter.publish(data.result, command()) == first
    loaded = adapter.load(first, data.query, data.scope, command())
    request = GenerationInput(
        request_id="generate",
        context=data.context,
        retrieved_skills=loaded,
        candidate_index=0,
        resample_index=0,
        seed=42,
        temperature=0.7,
    )
    assert request.retrieved_skills == tuple(r.skill for r in data.bank.records[:6])
    assert (
        "trajectory_ref" not in request.model_dump_json()
        and "review_ref" not in request.model_dump_json()
    )
    assert store.read(first) == data.result.model_dump_json().encode()


def test_authority_required_on_both_boundaries(tmp_path: Path) -> None:
    store, data, authority, adapter = setup(tmp_path)
    ref = adapter.publish(data.result, command())
    authority.denied = True
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OwnershipConflict):
        adapter.publish(data.result, command())
    with pytest.raises(OwnershipConflict):
        adapter.load(ref, data.query, data.scope, command())
    assert set((tmp_path / "blobs").iterdir()) == before


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
@pytest.mark.parametrize("item", ["split", "context", "skill", "review", "score"])
def test_missing_and_corrupt_transitive_bytes(
    tmp_path: Path, fault: str, item: str
) -> None:
    store, data, authority, adapter = setup(tmp_path)
    ref = adapter.publish(data.result, command())
    target = {
        "split": data.scope.split_ref,
        "context": data.query.public_context_ref,
        "skill": data.bank.records[7].skill_ref,
        "review": data.bank.records[7].sources[0].review_ref,
        "score": data.result.score_evidence_ref,
    }[item]
    path = tmp_path / "blobs" / target.sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"broken")
    expected = EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    with pytest.raises(expected):
        adapter.load(ref, data.query, data.scope, command())
    with pytest.raises(expected):
        adapter.publish(data.result, command())


@pytest.mark.parametrize("kind", ["query", "scope", "visibility", "schema"])
def test_wrong_consumer_binding_rejected(tmp_path: Path, kind: str) -> None:
    store, data, authority, adapter = setup(tmp_path)
    ref = adapter.publish(data.result, command())
    query, scope = data.query, data.scope
    if kind == "query":
        query = query.model_copy(update={"literal_goal": "other"})
    elif kind == "scope":
        scope = scope.model_copy(update={"excluded_source_ids": ("new",)})
    else:
        ref = ref.model_copy(
            update=(
                {"visibility": "public"}
                if kind == "visibility"
                else {"content_schema": "old/1"}
            )
        )
    with pytest.raises((ValueError, OwnershipConflict)):
        adapter.load(ref, query, scope, command())


@pytest.mark.parametrize("change", ["query", "encoder", "score", "proof"])
def test_scoring_receipt_content_must_bind_actual_execution(
    tmp_path: Path, change: str
) -> None:
    store, data, authority, adapter = setup(tmp_path)
    receipt = ScoringReceipt.model_validate_json(
        store.read(data.result.score_evidence_ref)
    )
    if change == "query":
        receipt = receipt.model_copy(
            update={
                "query": receipt.query.model_copy(update={"literal_goal": "different"})
            }
        )
    elif change == "encoder":
        receipt = receipt.model_copy(
            update={"encoder_ref": reference({"other": True}, store=store)}
        )
    elif change == "score":
        receipt = receipt.model_copy(update={"scores": tuple(reversed(receipt.scores))})
    else:
        execution = RetrievalExecution.model_validate_json(
            store.read(receipt.execution_ref)
        )
        execution = execution.model_copy(
            update={
                "encoded": execution.encoded.model_copy(
                    update={"model_files_sha256": "0" * 64}
                )
            }
        )
        receipt = receipt.model_copy(
            update={
                "execution_ref": reference(
                    execution, "retrieval-execution/1", store=store
                )
            }
        )
    ref = reference(receipt, "retrieval-scores/1", store=store)
    result = data.result.model_copy(update={"score_evidence_ref": ref})
    with pytest.raises(OwnershipConflict):
        adapter.publish(result, command())


def test_actual_skill_content_not_merely_valid_reference(tmp_path: Path) -> None:
    store, data, authority, adapter = setup(tmp_path)
    record = data.bank.records[-1].model_copy(
        update={
            "skill_ref": reference(skill("other"), "compact-skill/1", "public", store)
        }
    )
    bank = data.bank.model_copy(update={"records": (*data.bank.records[:-1], record)})
    scope = data.scope.model_copy(
        update={"bank_ref": reference(bank, "bank-manifest/1", store=store)}
    )
    result = data.result.model_copy(update={"scope": scope})
    with pytest.raises(OwnershipConflict, match="inline content"):
        adapter.publish(result, command())


def test_stored_context_must_match_query(tmp_path: Path) -> None:
    store, data, authority, adapter = setup(tmp_path)
    context = data.context.model_copy(
        update={"task": data.context.task.model_copy(update={"goal": "wrong"})}
    )
    query = data.query.model_copy(
        update={
            "public_context_ref": reference(
                context, "public-construction-context/1", "public", store
            )
        }
    )
    with pytest.raises(OwnershipConflict, match="public context"):
        adapter.publish(data.result.model_copy(update={"query": query}), command())


@pytest.mark.parametrize("bad", [None, {}, [], True])
def test_bad_input_has_no_publication_side_effect(tmp_path: Path, bad: object) -> None:
    store, data, authority, adapter = setup(tmp_path)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(ValidationError):
        adapter.publish(cast(RetrievalResult, bad), command())
    assert set((tmp_path / "blobs").iterdir()) == before


def test_cancel_and_cleanup_scope(tmp_path: Path) -> None:
    store, data, authority, adapter = setup(tmp_path)
    ref = adapter.publish(data.result, command())
    cleanup = command(cleanup_parent="parent")
    assert len(adapter.load(ref, data.query, data.scope, cleanup)) == 6
    with pytest.raises(OwnershipConflict):
        adapter.publish(data.result, cleanup)
    with pytest.raises(OwnershipConflict):
        adapter.load(ref, data.query, data.scope, command(attempt="attempt"))
    switch = CancelSwitch()
    switch.cancelled = True
    adapter.controls = OperationGuards(SystemClock(), switch)
    op = command().model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="unit", run_id="run", owner_id="owner"
            )
        }
    )
    with pytest.raises(OperationStopped):
        adapter.publish(data.result, op)


def test_publication_lost_ack_keeps_immutable_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, data, authority, adapter = setup(tmp_path)
    original = store.put
    retained: list[EvidenceRef] = []

    def lost(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        ref = original(data, metadata)
        retained.append(ref)
        raise OSError("lost ack")

    with monkeypatch.context() as scoped:
        scoped.setattr(store, "put", lost)
        with pytest.raises(OSError, match="lost ack"):
            adapter.publish(data.result, command())
    assert adapter.publish(data.result, command()) == retained[0]
    assert len(adapter.load(retained[0], data.query, data.scope, command())) == 6


@pytest.mark.parametrize("change", ["scores", "query", "scope"])
def test_consumer_rejects_valid_cas_with_wrong_execution_facts(
    tmp_path: Path, change: str
) -> None:
    store, data, authority, adapter = setup(tmp_path)
    receipt = ScoringReceipt.model_validate_json(
        store.read(data.result.score_evidence_ref)
    )
    execution = RetrievalExecution.model_validate_json(
        store.read(receipt.execution_ref)
    )
    if change == "scores":
        execution = execution.model_copy(
            update={
                "encoded": execution.encoded.model_copy(
                    update={"scores": (0.5,) * len(data.result.scores)}
                )
            }
        )
    elif change == "query":
        execution = execution.model_copy(
            update={
                "query": execution.query.model_copy(
                    update={"literal_goal": "different"}
                )
            }
        )
    else:
        execution = execution.model_copy(
            update={
                "scope": execution.scope.model_copy(
                    update={"excluded_source_ids": ("other-source",)}
                )
            }
        )
    receipt = receipt.model_copy(
        update={
            "execution_ref": reference(execution, "retrieval-execution/1", store=store)
        }
    )
    result = data.result.model_copy(
        update={
            "score_evidence_ref": reference(receipt, "retrieval-scores/1", store=store)
        }
    )
    raw_result = reference(result, "retrieval-result/1", store=store)
    before = set((tmp_path / "blobs").iterdir())
    with pytest.raises(OwnershipConflict):
        adapter.publish(result, command())
    with pytest.raises(OwnershipConflict):
        adapter.load(raw_result, data.query, data.scope, command())
    assert set((tmp_path / "blobs").iterdir()) == before
