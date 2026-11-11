"""CPU retrieval orchestration with real CAS and explicit unit qualification."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.adapters.retrieval.cpu_encoder import CpuEncoder
from lab_generate_skill.adapters.retrieval.retriever import CpuSkillRetriever
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.bank import BankManifest
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.domain.encoding import EncodedScores
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceNotFound,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext, CancellationRef
from lab_generate_skill.domain.retrieval import (
    RetrievalQuery,
    RetrievalScope,
    ScoringReceipt,
    RetrievalCommitUnconfirmed,
)
from lab_generate_skill.domain.retrieval_encoding import (
    RetrievalIndex,
    IndexEntry,
    document_texts,
)
from lab_generate_skill.domain.retrieval_execution import RetrievalExecution
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards

from encoder_fixtures import files, config, Loader, control
from retrieval_fixtures import fixture, reference, RetrievalFixture
from test_retrieval_evidence import UnitAuthority
from test_run_journal import command, CancelSwitch
from test_lifecycle import ManualClock


class UnitAdmission:
    def __init__(self) -> None:
        self.denied = False
        self.calls = 0

    def admit(
        self,
        query: RetrievalQuery,
        scope: RetrievalScope,
        bank: BankManifest,
        split: SplitManifest,
        op: OperationContext,
    ) -> None:
        self.calls += 1
        if self.denied or (op.run_id, op.owner_id) != ("run", "owner"):
            raise OwnershipConflict("Unit admission rejected")
        assert split.member(query.task).public_goal == query.literal_goal


@dataclass
class Harness:
    root: Path
    store: FileEvidenceStore
    data: RetrievalFixture
    loader: Loader
    encoder: CpuEncoder
    admission: UnitAdmission
    retriever: CpuSkillRetriever
    records: EvidenceRetrievalRecords


def setup(root: Path) -> Harness:
    (root / "evidence").mkdir()
    (root / "model").mkdir()
    store = FileEvidenceStore(root / "evidence")
    manifest = files(root / "model")
    settings = config()
    data = fixture(store, encoder_files=manifest, encoder_config=settings)
    loader = Loader()
    encoder = CpuEncoder(root / "model", manifest, settings, loader=loader)
    guards = OperationGuards(SystemClock(), CancelSwitch())
    admission = UnitAdmission()
    return Harness(
        root,
        store,
        data,
        loader,
        encoder,
        admission,
        CpuSkillRetriever(store, guards, encoder, admission),
        EvidenceRetrievalRecords(store, guards, UnitAuthority(store)),
    )


def test_complete_retrieve_publish_consume_and_exact_batch_reuse(
    tmp_path: Path,
) -> None:
    h = setup(tmp_path)
    first = h.retriever.retrieve(h.data.query, h.data.scope, 6, command())
    reference = h.records.publish(first, command())
    skills = h.records.load(reference, h.data.query, h.data.scope, command())
    request = GenerationInput(
        request_id="generator",
        context=h.data.context,
        retrieved_skills=skills,
        candidate_index=0,
        resample_index=0,
        seed=42,
        temperature=0.7,
    )
    assert (
        len(request.retrieved_skills) == 6
        and "trajectory_ref" not in request.model_dump_json()
    )
    second = h.retriever.retrieve(h.data.query, h.data.scope, 6, command())
    assert (
        first.hits == second.hits
        and h.loader.calls == 1
        and len(h.loader.model.calls) == 3
    )
    scores = ScoringReceipt.model_validate_json(h.store.read(second.score_evidence_ref))
    assert RetrievalExecution.model_validate_json(
        h.store.read(scores.execution_ref)
    ).encoded.documents_reused
    assert h.loader.model.calls[0] == document_texts(h.data.bank.records)


@pytest.mark.parametrize("k", [None, True, 6.0, "6", 0, 5, 7])
def test_bad_k_before_model_or_new_evidence(tmp_path: Path, k: object) -> None:
    h = setup(tmp_path)
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises(ValueError):
        h.retriever.retrieve(h.data.query, h.data.scope, cast(int, k), command())
    assert (
        h.loader.calls == 0 and set((tmp_path / "evidence/blobs").iterdir()) == before
    )


def test_admission_denial_precedes_encoding_and_writes(tmp_path: Path) -> None:
    h = setup(tmp_path)
    h.admission.denied = True
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises(OwnershipConflict):
        h.retriever.retrieve(h.data.query, h.data.scope, 6, command())
    assert (
        h.admission.calls == 1
        and h.loader.calls == 0
        and set((tmp_path / "evidence/blobs").iterdir()) == before
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing_skill",
        "index_order",
        "model_binding",
        "too_few",
        "bad_query",
        "old_artifact",
    ],
)
def test_preflight_failure_does_not_load_model(tmp_path: Path, fault: str) -> None:
    h = setup(tmp_path)
    query, scope = h.data.query, h.data.scope
    bank = h.data.bank
    if fault == "missing_skill":
        (tmp_path / "evidence/blobs" / bank.records[-1].skill_ref.sha256).unlink()
    elif fault == "index_order":
        index = RetrievalIndex(
            entries=tuple(
                IndexEntry(skill_id=r.skill_id, content_digest=r.content_digest)
                for r in reversed(bank.records)
            )
        )
        bank = bank.model_copy(
            update={"index_ref": reference(index, "retrieval-index/1", store=h.store)}
        )
    elif fault == "model_binding":
        bank = bank.model_copy(
            update={
                "retrieval_config_ref": reference(
                    h.encoder.config.model_copy(update={"cpu_threads": 3}),
                    "encoder-config/1",
                    store=h.store,
                )
            }
        )
    elif fault == "old_artifact":
        bank = bank.model_copy(
            update={"encoder_ref": reference({"placeholder": True}, store=h.store)}
        )
    elif fault == "too_few":
        scope = scope.model_copy(
            update={"excluded_source_ids": tuple("runtime-" + str(i) for i in range(3))}
        )
    else:
        query = query.model_copy(update={"literal_goal": "different"})
    if bank != h.data.bank:
        scope = scope.model_copy(
            update={"bank_ref": reference(bank, "bank-manifest/1", store=h.store)}
        )
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises((ValueError, OwnershipConflict, EvidenceNotFound)):
        h.retriever.retrieve(query, scope, 6, command())
    assert (
        h.loader.calls == 0 and set((tmp_path / "evidence/blobs").iterdir()) == before
    )


@pytest.mark.parametrize("phase", ["execute_before", "score_before", "score_after"])
def test_publication_fault_reconciliation_never_encodes_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    h = setup(tmp_path)
    op = command()
    original = h.store.put

    def fail(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        target = (
            "retrieval-execution/1"
            if phase == "execute_before"
            else "retrieval-scores/1"
        )
        if metadata.content_schema == target:
            if phase == "score_after":
                original(data, metadata)
            raise OSError("unit publication failure")
        return original(data, metadata)

    with monkeypatch.context() as scoped:
        scoped.setattr(h.store, "put", fail)
        if phase == "execute_before":
            with pytest.raises(OSError):
                h.retriever.retrieve(h.data.query, h.data.scope, 6, op)
            assert len(h.loader.model.calls) == 2
            return
        with pytest.raises(RetrievalCommitUnconfirmed) as caught:
            h.retriever.retrieve(h.data.query, h.data.scope, 6, op)
    assert isinstance(caught.value.__cause__, OSError)
    saved = RetrievalExecution.model_validate_json(
        h.store.read(caught.value.execution_ref)
    )
    assert saved.operation == op
    h.encoder.close(control())
    cleanup = command(cleanup_parent=op.operation_id)
    result = h.retriever.reconcile(
        h.data.query, h.data.scope, 6, caught.value.execution_ref, cleanup
    )
    assert (
        h.retriever.reconcile(
            h.data.query, h.data.scope, 6, caught.value.execution_ref, command()
        )
        == result
    )
    published = h.records.publish(result, command())
    assert len(h.records.load(published, h.data.query, h.data.scope, command())) == 6
    assert len(h.loader.model.calls) == 2


@pytest.mark.parametrize("change", ["context", "owner", "parent", "schema", "scores"])
def test_wrong_reconciliation_binding_rejected(tmp_path: Path, change: str) -> None:
    h = setup(tmp_path)
    op = command()
    result = h.retriever.retrieve(h.data.query, h.data.scope, 6, op)
    receipt = ScoringReceipt.model_validate_json(
        h.store.read(result.score_evidence_ref)
    )
    execution_ref = receipt.execution_ref
    query, scope = h.data.query, h.data.scope
    retry = command(cleanup_parent=op.operation_id)
    if change == "context":
        query = query.model_copy(
            update={
                "public_context_ref": reference(
                    h.data.context.model_copy(update={"context_id": "other"}),
                    "public-construction-context/1",
                    "public",
                    h.store,
                )
            }
        )
    elif change == "owner":
        retry = retry.model_copy(update={"owner_id": "other"})
    elif change == "parent":
        retry = command(cleanup_parent="wrong")
    elif change == "schema":
        execution_ref = execution_ref.model_copy(update={"content_schema": "old/1"})
    else:
        execution = RetrievalExecution.model_validate_json(h.store.read(execution_ref))
        execution = execution.model_copy(
            update={"encoded": execution.encoded.model_copy(update={"scores": (0.0,)})}
        )
        execution_ref = reference(execution, "retrieval-execution/1", store=h.store)
    with pytest.raises((ValueError, OwnershipConflict)):
        h.retriever.reconcile(query, scope, 6, execution_ref, retry)
    assert len(h.loader.model.calls) == 2


@pytest.mark.parametrize(
    "field",
    [
        "model_files_sha256",
        "config_sha256",
        "documents_sha256",
        "query_sha256",
        "scores",
    ],
)
def test_unbound_encoder_output_not_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    h = setup(tmp_path)
    original = h.encoder.score

    def corrupt(
        documents: tuple[str, ...], query: str, control: OperationControl
    ) -> EncodedScores:
        result = original(documents, query, control)
        return result.model_copy(
            update={field: (1.0,) if field == "scores" else "0" * 64}
        )

    monkeypatch.setattr(h.encoder, "score", corrupt)
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises(OwnershipConflict):
        h.retriever.retrieve(h.data.query, h.data.scope, 6, command())
    assert set((tmp_path / "evidence/blobs").iterdir()) == before


def test_cancelled_and_cleanup_operations_do_not_encode(tmp_path: Path) -> None:
    h = setup(tmp_path)
    with pytest.raises(OwnershipConflict):
        h.retriever.retrieve(
            h.data.query, h.data.scope, 6, command(cleanup_parent="parent")
        )
    switch = CancelSwitch()
    switch.cancelled = True
    h.retriever.controls = OperationGuards(SystemClock(), switch)
    op = command().model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="cancel", run_id="run", owner_id="owner"
            )
        }
    )
    with pytest.raises(OperationStopped):
        h.retriever.retrieve(h.data.query, h.data.scope, 6, op)
    assert h.loader.calls == 0


@pytest.mark.parametrize("field", ["root", "files", "config"])
def test_encoder_binding_cannot_be_swapped_after_construction(
    tmp_path: Path, field: str
) -> None:
    h = setup(tmp_path)
    with pytest.raises(AttributeError):
        setattr(h.encoder, field, None)


@pytest.mark.parametrize("bad", [None, [], {}, True])
def test_bad_query_rejected_before_model(tmp_path: Path, bad: object) -> None:
    h = setup(tmp_path)
    with pytest.raises(ValidationError):
        h.retriever.retrieve(cast(RetrievalQuery, bad), h.data.scope, 6, command())
    assert h.loader.calls == 0


@pytest.mark.parametrize("fault", ["raise", "nan", "shape"])
def test_encoder_failure_does_not_publish_or_restart(
    tmp_path: Path, fault: str
) -> None:
    h = setup(tmp_path)
    h.loader.model.bad = fault
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises((ValueError, RuntimeError)):
        h.retriever.retrieve(h.data.query, h.data.scope, 6, command())
    h.loader.model.bad = None
    with pytest.raises(RuntimeError, match="closed"):
        h.retriever.retrieve(h.data.query, h.data.scope, 6, command())
    assert h.loader.calls == 1 and len(h.loader.model.calls) == 1
    assert set((tmp_path / "evidence/blobs").iterdir()) == before


def test_expired_original_operation_reconciles_with_fresh_cleanup(
    tmp_path: Path,
) -> None:
    h = setup(tmp_path)
    clock = ManualClock()
    h.retriever.controls = OperationGuards(clock, CancelSwitch())
    original = command().model_copy(
        update={"deadline": clock.utcnow() + timedelta(seconds=10)}
    )
    result = h.retriever.retrieve(h.data.query, h.data.scope, 6, original)
    receipt = ScoringReceipt.model_validate_json(
        h.store.read(result.score_evidence_ref)
    )
    raw = h.store.read(receipt.execution_ref)
    h.encoder.close(control())
    clock.sleep(11)
    with pytest.raises(OperationStopped):
        h.retriever.reconcile(
            h.data.query, h.data.scope, 6, receipt.execution_ref, original
        )
    cleanup = original.cleanup("new-cleanup", now=clock.utcnow(), seconds=5)
    assert (
        h.retriever.reconcile(
            h.data.query, h.data.scope, 6, receipt.execution_ref, cleanup
        )
        == result
    )
    assert h.store.read(receipt.execution_ref) == raw
    assert RetrievalExecution.model_validate_json(raw).operation == original
    assert len(h.loader.model.calls) == 2
