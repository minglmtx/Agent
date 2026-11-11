"""Exact byte resolution and private CAS facts; no ledger or provider calls."""

from lab_generate_skill.ports.lifecycle import OperationControl

from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.model_request import ModelSendPlan, ResolvedModelRequest
from lab_generate_skill.domain.model_response import ModelSendFact
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.ports.evidence import EvidenceStore


class ModelSendEvidence:
    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    def resolve(
        self, plan: ModelSendPlan, control: OperationControl
    ) -> ResolvedModelRequest:
        return ResolvedModelRequest(
            request=plan.reservation.request,
            input_bytes=self._store.read(plan.input_ref, control=control),
            parameters_bytes=self._store.read(plan.parameters_ref, control=control),
            limits=plan.limits,
        )

    def response(
        self, plan: ModelSendPlan, data: bytes, control: OperationControl
    ) -> EvidenceRef:
        return self._store.put(
            data,
            EvidenceMetadata(
                media_type="application/octet-stream",
                visibility="private",
                content_schema=plan.reservation.request.role + "-model-response/1",
                producer="paid-model-sender-v1",
            ),
            control=control,
        )

    def publish(self, fact: ModelSendFact, control: OperationControl) -> EvidenceRef:
        return self._store.put(
            fact.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                visibility="private",
                content_schema="model-send-fact/1",
                producer="paid-model-sender-v1",
            ),
            control=control,
        )

    def load(
        self, plan: ModelSendPlan, ref: EvidenceRef, control: OperationControl
    ) -> ModelSendFact:
        ref = EvidenceRef.model_validate(ref)
        private_state_ref(ref, "model-send-fact/1")
        if ref.size_bytes > 128 * 1024:
            raise ValueError("Model fact envelope exceeds bounded read size")
        fact = ModelSendFact.model_validate_json(self._store.read(ref, control=control))
        if fact.request != plan.reservation.request or fact.operation != plan.operation:
            raise OwnershipConflict("Saved response belongs to another model send")
        if fact.response_ref.size_bytes > plan.limits.max_response_bytes:
            raise ValueError("Saved response exceeds frozen response limit")
        self._store.read(fact.response_ref, control=control)
        return fact
