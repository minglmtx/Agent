"""Actual MiniLM retrieval/consumption with explicitly synthetic provenance.

Called only on the compute worker by encoder_live_check. This is an integration
fixture, never a production admission authority or a formal training source.
"""

from pathlib import Path

import numpy as np

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.adapters.retrieval.cpu_encoder import CpuEncoder
from lab_generate_skill.adapters.retrieval.retriever import CpuSkillRetriever
from lab_generate_skill.adapters.retrieval.sentence_model import SentenceModel
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.retrieval import ScoringReceipt
from lab_generate_skill.domain.retrieval_execution import RetrievalExecution
from lab_generate_skill.runtime.lifecycle import OperationGuards

from encoder_fixtures import control
from retrieval_fixtures import fixture
from test_cpu_retriever import UnitAdmission
from test_retrieval_evidence import UnitAuthority
from test_run_journal import command, CancelSwitch


def verify_retriever(
    root: Path, output: Path, backend: CpuEncoder, old: SentenceModel
) -> dict[str, object]:
    root.mkdir()
    store = FileEvidenceStore(root)
    data = fixture(store, encoder_files=backend.files, encoder_config=backend.config)
    guards = OperationGuards(SystemClock(), CancelSwitch())
    retriever = CpuSkillRetriever(store, guards, backend, UnitAdmission())
    records = EvidenceRetrievalRecords(store, guards, UnitAuthority(store))
    operation = command()
    result = retriever.retrieve(data.query, data.scope, 6, operation)
    reference = records.publish(result, command())
    skills = records.load(reference, data.query, data.scope, command())
    generated = GenerationInput(
        request_id="live-generator-fixture",
        context=data.context,
        retrieved_skills=skills,
        candidate_index=0,
        resample_index=0,
        seed=42,
        temperature=0.7,
    )
    # Independent original template; do not derive both sides via document_texts.
    documents = [
        f"Title: {r.skill.title}\nPrinciple: {r.skill.principle}\nWhen to apply: {r.skill.when_to_apply}"
        for r in data.bank.records
    ]
    vectors = old.encode(
        documents, normalize_embeddings=True, batch_size=32, show_progress_bar=False
    )
    query = old.encode(
        [data.query.literal_goal],
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    )[0]
    expected = vectors @ query
    actual = np.asarray([s.score for s in result.scores], dtype=np.float32)
    if not np.array_equal(expected, actual):
        raise AssertionError("Wired retrieval scores differ from original CPU calls")
    order = sorted(
        range(len(data.bank.records)),
        key=lambda i: (-float(expected[i]), data.bank.records[i].skill_id),
    )[:6]
    expected_skills = tuple(data.bank.records[i].skill for i in order)
    if generated.retrieved_skills != expected_skills:
        raise AssertionError("Generator received wrong ordered public skills")
    if (
        "trajectory_ref" in generated.model_dump_json()
        or "review_ref" in generated.model_dump_json()
    ):
        raise AssertionError("Private source references leaked into generation input")
    first = ScoringReceipt.model_validate_json(store.read(result.score_evidence_ref))
    execution = RetrievalExecution.model_validate_json(store.read(first.execution_ref))
    second = retriever.retrieve(data.query, data.scope, 6, command())
    second_receipt = ScoringReceipt.model_validate_json(
        store.read(second.score_evidence_ref)
    )
    second_execution = RetrievalExecution.model_validate_json(
        store.read(second_receipt.execution_ref)
    )
    if second.hits != result.hits or not second_execution.encoded.documents_reused:
        raise AssertionError("Complete-batch reuse changed wired retrieval")
    backend.close(control())
    reconciled = retriever.reconcile(
        data.query,
        data.scope,
        6,
        first.execution_ref,
        command(cleanup_parent=operation.operation_id),
    )
    if (
        reconciled != result
        or retriever.reconcile(
            data.query, data.scope, 6, first.execution_ref, command()
        )
        != result
    ):
        raise AssertionError("Closed-model reconciliation changed original result")
    if (
        records.load(
            records.publish(reconciled, command()), data.query, data.scope, command()
        )
        != expected_skills
    ):
        raise AssertionError("Reconciled consumer output differs")
    retained = output / "retriever"
    retained.mkdir()
    for name, value in [
        ("bank", data.bank),
        ("split", data.split),
        ("context", data.context),
        ("result", result),
        ("execution", execution),
        ("cached-execution", second_execution),
        ("generation-input", generated),
    ]:
        (retained / (name + ".json")).write_text(value.model_dump_json(indent=2) + "\n")
    # Preserve actual CAS bytes as well as the selected readable evidence.
    import shutil

    shutil.copytree(root / "blobs", retained / "blobs")
    return dict(
        passed=True,
        documents=len(documents),
        max_absolute_error=float(np.max(np.abs(expected - actual))),
        top6=[data.bank.records[i].skill_id for i in order],
        complete_batch_reused=True,
        closed_encoder_reconciliation=True,
        evidence=str(retained),
        provenance="synthetic unit bank, admission and authority; actual offline MiniLM and CAS",
        formal_training_qualified=False,
    )
