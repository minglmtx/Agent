"""Original provider response and settlement facts; never a resend token."""

from typing import Literal, Self
from pydantic import model_validator
from .budget import Money
from .evidence import EvidenceRef
from .generation import RequestIdentity, OutcomeProof, RequestReceipt
from .lifecycle import OperationContext
from .model_request import check_model_operation
from .state_scope import private_state_ref
from .validation import Contract, Identifier, NonEmptyText


class ProviderReply(Contract):
    """Completed response, including empty content; unknown cost remains unknown.

    Transport must retain exact provider bytes and validate its response identity.
    Rejection/timeout/partial response must not be invented as a completed reply.
    """

    request_id: Identifier
    provider_request_id: NonEmptyText
    raw_response: bytes
    charge: Money | None


class ModelSendFact(Contract):
    schema_version: Literal["model-send-fact/1"] = "model-send-fact/1"
    request: RequestIdentity
    operation: OperationContext
    response_ref: EvidenceRef
    provider_request_id: NonEmptyText
    charge: Money | None

    @model_validator(mode="after")
    def bound_response(self) -> Self:
        check_model_operation(self.request, self.operation)
        if self.operation.mode != "execute":
            raise ValueError("Response retains original execution operation")
        private_state_ref(self.response_ref, self.request.role + "-model-response/1")
        return self

    def proof(self, fact_ref: EvidenceRef) -> OutcomeProof:
        private_state_ref(fact_ref, "model-send-fact/1")
        return OutcomeProof(
            request=self.request,
            outcome="uncertain" if self.charge is None else "succeeded",
            evidence=(fact_ref,),
            response_ref=self.response_ref,
            provider_request_id=self.provider_request_id,
            charge=self.charge,
        )


class ModelSendResult(Contract):
    schema_version: Literal["model-send-result/1"] = "model-send-result/1"
    fact: ModelSendFact
    fact_ref: EvidenceRef
    settlement: RequestReceipt

    @model_validator(mode="after")
    def original_settlement(self) -> Self:
        proof = self.fact.proof(self.fact_ref)
        if self.settlement.record.reservation.request != self.fact.request or (
            self.settlement.proof_sha256 != proof.digest
        ):
            raise ValueError("Send result must retain the exact original settlement")
        return self


class ModelSendUnconfirmed(RuntimeError):
    """Dispatch may have committed. Inspect/reconcile; never automatically resend.

    Known references survive response/fact/settlement/checkpoint failures. The
    original exception (including cleanup groups) is retained as __cause__.
    This exception does not claim the provider was or was not called.
    """

    def __init__(
        self,
        request_id: str,
        stage: str,
        response_ref: EvidenceRef | None,
        fact_ref: EvidenceRef | None,
        transport_ref: EvidenceRef | None = None,
    ) -> None:
        self.request_id, self.stage = request_id, stage
        self.response_ref, self.fact_ref = response_ref, fact_ref
        self.transport_ref = transport_ref
        super().__init__(f"Model send unconfirmed at {stage}: {request_id}")


class ModelTransportFailure(RuntimeError):
    """Saved provider/HTTP failure is diagnostic, not proof of non-execution."""

    def __init__(self, reason: str, reference: EvidenceRef) -> None:
        private_state_ref(reference, "model-transport-failure/1")
        self.reason_code, self.reference = reason, reference
        super().__init__(f"Model transport failed: {reason}")
