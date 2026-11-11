"""Stored transport failure and verified charged failure; never model success."""

from typing import Literal, Self
from pydantic import Field, model_validator
from .budget import Money
from .evidence import EvidenceRef
from .generation import RequestIdentity, OutcomeProof, RequestReceipt
from .lifecycle import OperationContext
from .model_request import check_model_operation
from .state_scope import private_state_ref
from .validation import Contract, NonEmptyText


class TransportDiagnostic(Contract):
    schema_version: Literal["model-transport-failure/1"] = "model-transport-failure/1"
    request: RequestIdentity
    operation: OperationContext
    reason: NonEmptyText
    status: int | None = Field(ge=100, le=599)
    body_base64: str
    error_types: tuple[str, ...]

    @model_validator(mode="after")
    def scope(self) -> Self:
        check_model_operation(self.request, self.operation)
        if self.operation.mode != "execute":
            raise ValueError("Diagnostic must retain original send operation")
        return self


class ModelFailureFact(Contract):
    schema_version: Literal["model-failure-billing/1"] = "model-failure-billing/1"
    request: RequestIdentity
    operation: OperationContext
    transport_ref: EvidenceRef
    response_ref: EvidenceRef
    provider_request_id: NonEmptyText
    charge: Money

    @model_validator(mode="after")
    def binding(self) -> Self:
        check_model_operation(self.request, self.operation)
        if self.operation.mode != "execute":
            raise ValueError("Failure billing retains original send operation")
        private_state_ref(self.transport_ref, "model-transport-failure/1")
        private_state_ref(self.response_ref, self.request.role + "-model-response/1")
        return self

    def proof(self, fact_ref: EvidenceRef) -> OutcomeProof:
        private_state_ref(fact_ref, "model-failure-billing/1")
        return OutcomeProof(
            request=self.request,
            outcome="charged_failure",
            evidence=(fact_ref,),
            response_ref=self.response_ref,
            provider_request_id=self.provider_request_id,
            charge=self.charge,
        )


class FailureBillingResult(Contract):
    schema_version: Literal["failure-billing-result/1"] = "failure-billing-result/1"
    fact: ModelFailureFact
    fact_ref: EvidenceRef
    settlement: RequestReceipt

    @model_validator(mode="after")
    def failed_charge_only(self) -> Self:
        if (
            self.settlement.record.state != "charged_failure"
            or self.settlement.record.reservation.request != self.fact.request
            or (self.settlement.proof_sha256 != self.fact.proof(self.fact_ref).digest)
        ):
            raise ValueError("Failure billing must retain exact failed charge receipt")
        return self


class FailureBillingPending(RuntimeError):
    """Only reconcile original stored failure; no provider call is permitted."""

    def __init__(
        self,
        transport_ref: EvidenceRef,
        response_ref: EvidenceRef | None,
        fact_ref: EvidenceRef | None,
    ) -> None:
        self.transport_ref, self.response_ref, self.fact_ref = (
            transport_ref,
            response_ref,
            fact_ref,
        )
        super().__init__("Original failure billing remains unconfirmed")
