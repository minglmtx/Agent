"""Verify full bank/split/input/score bytes at publication and consumption.

This adapter performs no encoding, website actions, model calls or qualification
fallback. A mandatory authority checks semantics beyond the versioned documents.
The consumer receives exactly six ordered public CompactSkills, no private trace.
"""

from lab_generate_skill.adapters.plans.retrieval_inputs import RetrievalInputReader
from lab_generate_skill.domain.retrieval_execution import RetrievalExecution
from lab_generate_skill.domain.retrieval_encoding import (
    document_texts,
    validate_encoded,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.retrieval import (
    RetrievalQuery,
    RetrievalScope,
    RetrievalResult,
    ScoringReceipt,
    validate_retrieval,
)
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.retrieval import RetrievalAuthority


class EvidenceRetrievalRecords:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        authority: RetrievalAuthority,
    ) -> None:
        self.store, self.controls, self.authority = store, controls, authority
        self.inputs = RetrievalInputReader(store)

    def _guard(
        self, op: OperationContext, *, writing: bool = False
    ) -> OperationControl:
        op = OperationContext.model_validate(op)
        if op.attempt_id is not None or (writing and op.mode != "execute"):
            raise OwnershipConflict("Retrieval transport requires run-level operation")
        control = self.controls.bind(op)
        control.checkpoint()
        return control

    def _read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        raw = self.store.read(ref, control=control)
        control.checkpoint()
        return raw

    def _verify(
        self, result: RetrievalResult, op: OperationContext, control: OperationControl
    ) -> tuple[CompactSkill, ...]:
        inputs = self.inputs.load(result.query, result.scope, control)
        bank, split = inputs.bank, inputs.split
        selected = validate_retrieval(result, bank, split)
        scores = ScoringReceipt.model_validate_json(
            self._read(result.score_evidence_ref, control)
        )
        if (
            scores.query,
            scores.scope,
            scores.encoder_ref,
            scores.tokenizer_ref,
            scores.index_ref,
            scores.config_ref,
            scores.scores,
        ) != (
            result.query,
            result.scope,
            bank.encoder_ref,
            bank.tokenizer_ref,
            bank.index_ref,
            bank.retrieval_config_ref,
            result.scores,
        ):
            raise OwnershipConflict(
                "Scoring receipt does not bind this exact bank, query and ordered batch"
            )
        execution = RetrievalExecution.model_validate_json(
            self._read(scores.execution_ref, control)
        )
        if execution.query != result.query or execution.scope != result.scope:
            raise OwnershipConflict(
                "Execution evidence belongs to another query or scope"
            )
        encoded = execution.encoded
        validate_encoded(
            encoded,
            document_texts(inputs.eligible),
            result.query.literal_goal,
            inputs.files,
            inputs.config,
        )
        if encoded.scores != tuple(score.score for score in result.scores):
            raise OwnershipConflict(
                "Scoring receipt differs from actual encoded scores"
            )
        self.authority.verify(result, bank, split, op)
        control.checkpoint()
        return tuple(record.skill for record in selected)

    def publish(self, result: RetrievalResult, op: OperationContext) -> EvidenceRef:
        result = RetrievalResult.model_validate(result)
        control = self._guard(op, writing=True)
        self._verify(result, op, control)
        ref = self.store.put(
            result.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="retrieval-result/1",
                visibility="private",
                producer="retrieval-records-v1",
            ),
            control=control,
        )
        control.checkpoint()
        return ref

    def load(
        self,
        reference: EvidenceRef,
        query: RetrievalQuery,
        scope: RetrievalScope,
        op: OperationContext,
    ) -> tuple[CompactSkill, ...]:
        reference = EvidenceRef.model_validate(reference)
        query = RetrievalQuery.model_validate(query)
        scope = RetrievalScope.model_validate(scope)
        if (
            reference.content_schema != "retrieval-result/1"
            or reference.visibility != "private"
        ):
            raise ValueError("Expected private retrieval-result/1")
        control = self._guard(op)
        result = RetrievalResult.model_validate_json(self._read(reference, control))
        if result.query != query or result.scope != scope:
            raise OwnershipConflict("Retrieval belongs to another query or scope")
        return self._verify(result, op, control)
