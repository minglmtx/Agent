"""CPU SkillRetriever: preflight -> admission -> encode -> immutable receipts.

The worker owns the injected encoder lifecycle. No automatic replay/retry or
default qualification. Known encoded bytes can be reconciled without encoding;
the result consumer independently rechecks the same frozen inputs and scores.
"""

from lab_generate_skill.adapters.plans.retrieval_inputs import (
    RetrievalInputReader,
    RetrievalInputs,
)
from lab_generate_skill.domain.encoding import EncodedScores
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.retrieval import (
    RetrievalQuery,
    RetrievalScope,
    RetrievalResult,
    ScoringReceipt,
    SkillScore,
    RetrievalCommitUnconfirmed,
    rank_retrieval,
)
from lab_generate_skill.domain.retrieval_encoding import (
    document_texts,
    validate_encoded,
)
from lab_generate_skill.domain.retrieval_execution import RetrievalExecution
from lab_generate_skill.ports.encoding import ScoreEncoder
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.retrieval import RetrievalAdmission


class CpuSkillRetriever:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        encoder: ScoreEncoder,
        admission: RetrievalAdmission,
    ) -> None:
        self.store, self.controls, self.encoder, self.admission = (
            store,
            controls,
            encoder,
            admission,
        )
        self.inputs = RetrievalInputReader(store)

    def _prepare(
        self,
        query: RetrievalQuery,
        scope: RetrievalScope,
        k: int,
        op: OperationContext,
        *,
        encoding: bool,
    ) -> tuple[RetrievalInputs, OperationControl]:
        query = RetrievalQuery.model_validate(query)
        scope = RetrievalScope.model_validate(scope)
        op = OperationContext.model_validate(op)
        if type(k) is not int or k != 6:
            raise ValueError("Retrieval requires exact integer k=6")
        if op.attempt_id is not None or (encoding and op.mode != "execute"):
            raise OwnershipConflict(
                "Encoding requires run-level execute; cleanup can only reconcile"
            )
        control = self.controls.bind(op)
        control.checkpoint()
        inputs = self.inputs.load(query, scope, control)
        if inputs.files != self.encoder.files or inputs.config != self.encoder.config:
            raise OwnershipConflict(
                "Encoder instance differs from frozen bank artifacts"
            )
        self.admission.admit(query, scope, inputs.bank, inputs.split, op)
        control.checkpoint()
        return inputs, control

    def _put(
        self,
        value: RetrievalExecution | ScoringReceipt,
        schema: str,
        control: OperationControl,
    ) -> EvidenceRef:
        return self.store.put(
            value.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="cpu-retriever-v1",
            ),
            control=control,
        )

    def _finish(
        self,
        encoded: EncodedScores,
        execution_ref: EvidenceRef,
        query: RetrievalQuery,
        scope: RetrievalScope,
        inputs: RetrievalInputs,
        control: OperationControl,
    ) -> RetrievalResult:
        try:
            control.checkpoint()
            scores = tuple(
                SkillScore(skill_id=r.skill_id, score=score)
                for r, score in zip(inputs.eligible, encoded.scores, strict=True)
            )
            bank = inputs.bank
            receipt = ScoringReceipt(
                query=query,
                scope=scope,
                encoder_ref=bank.encoder_ref,
                tokenizer_ref=bank.tokenizer_ref,
                index_ref=bank.index_ref,
                config_ref=bank.retrieval_config_ref,
                scores=scores,
                execution_ref=execution_ref,
            )
            reference = self._put(receipt, "retrieval-scores/1", control=control)
            control.checkpoint()
            return rank_retrieval(query, scope, bank, inputs.split, scores, reference)
        except Exception as error:
            raise RetrievalCommitUnconfirmed(execution_ref) from error

    def retrieve(
        self, query: RetrievalQuery, scope: RetrievalScope, k: int, op: OperationContext
    ) -> RetrievalResult:
        query = RetrievalQuery.model_validate(query)
        scope = RetrievalScope.model_validate(scope)
        op = OperationContext.model_validate(op)
        inputs, control = self._prepare(query, scope, k, op, encoding=True)
        documents = document_texts(inputs.eligible)
        encoded = validate_encoded(
            self.encoder.score(documents, query.literal_goal, control),
            documents,
            query.literal_goal,
            inputs.files,
            inputs.config,
        )
        control.checkpoint()
        reference = self._put(
            RetrievalExecution(query=query, scope=scope, operation=op, encoded=encoded),
            "retrieval-execution/1",
            control=control,
        )
        return self._finish(encoded, reference, query, scope, inputs, control)

    def reconcile(
        self,
        query: RetrievalQuery,
        scope: RetrievalScope,
        k: int,
        execution_ref: EvidenceRef,
        op: OperationContext,
    ) -> RetrievalResult:
        query = RetrievalQuery.model_validate(query)
        scope = RetrievalScope.model_validate(scope)
        op = OperationContext.model_validate(op)
        execution_ref = EvidenceRef.model_validate(execution_ref)
        if (
            execution_ref.content_schema != "retrieval-execution/1"
            or execution_ref.visibility != "private"
        ):
            raise ValueError("Reconciliation needs private retrieval-execution/1")
        inputs, control = self._prepare(query, scope, k, op, encoding=False)
        execution = RetrievalExecution.model_validate_json(
            self.inputs.read(execution_ref, control)
        )
        if execution.query != query or execution.scope != scope:
            raise OwnershipConflict(
                "Cannot reconcile evidence from another query or scope"
            )
        execution.check_reconciliation(op)
        encoded = execution.encoded
        validate_encoded(
            encoded,
            document_texts(inputs.eligible),
            query.literal_goal,
            inputs.files,
            inputs.config,
        )
        return self._finish(encoded, execution_ref, query, scope, inputs, control)
