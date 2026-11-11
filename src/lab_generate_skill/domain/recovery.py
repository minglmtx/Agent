"""Original-resource recovery contracts; data is never takeover authority.

Termination evidence is checked by an authority adapter under an exclusive
recovery session. Receipts distinguish restored task state from provider close.
Neither successful recovery nor diagnostic quarantine grants training admission.
"""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .evidence import EvidenceRef
from .lifecycle import AllocationToken, CleanupFailure, ResourceOwner
from .validation import Contract, Identifier, NonEmptyText


class WriterTerminationReceipt(Contract):
    """Confirmed end of the exact writer and its effect-producing descendants."""

    schema_version: Literal["writer-termination/1"] = "writer-termination/1"
    owner: ResourceOwner
    writer_instance_id: Identifier
    authority_id: Identifier
    authority_version: NonEmptyText
    observed_at: AwareDatetime
    status: Literal["terminated"] = "terminated"
    descendants_terminated: Literal[True]
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)

    @field_validator("descendants_terminated", mode="before")
    @classmethod
    def exact_confirmation(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("Descendant termination needs explicit boolean true")
        return True

    @model_validator(mode="after")
    def private_proof(self) -> Self:
        if any(ref.visibility != "private" for ref in self.evidence):
            raise ValueError("Writer termination proof must remain private")
        return self


class RecoveryBinding(Contract):
    """Frozen executor/provider combination, supplied by explicit registration."""

    schema_version: Literal["recovery-binding/1"] = "recovery-binding/1"
    component_id: Identifier
    component_version: NonEmptyText
    provider_id: Identifier
    provider_version: NonEmptyText
    resource_kind: Identifier


class RecoveryIntent(Contract):
    """Durable before effects, also identifying the new recovery writer."""

    schema_version: Literal["recovery-intent/1"] = "recovery-intent/1"
    allocation: AllocationToken
    binding: RecoveryBinding
    recovery_writer: ResourceOwner
    operation_id: Identifier
    termination: WriterTerminationReceipt

    @model_validator(mode="after")
    def identities(self) -> Self:
        if self.termination.owner != self.allocation.owner:
            raise ValueError("Termination must identify the original resource writer")
        if self.recovery_writer == self.allocation.owner:
            raise ValueError("Recovery requires a separately identified live writer")
        if self.recovery_writer.run_id != self.allocation.owner.run_id:
            raise ValueError("Recovery writer must belong to the original run")
        if (
            self.binding.provider_id,
            self.binding.provider_version,
            self.binding.resource_kind,
        ) != (
            self.allocation.provider_id,
            self.allocation.provider_version,
            self.allocation.resource_kind,
        ):
            raise ValueError("Recovery binding must preserve the original provider")
        return self


class RecoveryObservation(Contract):
    """Read-only identity inspection; absence does not authorize recreation."""

    schema_version: Literal["recovery-observation/1"] = "recovery-observation/1"
    allocation_id: Identifier
    actual_resource_id: Identifier | None
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)


class RecoveryCheck(Contract):
    schema_version: Literal["recovery-check/1"] = "recovery-check/1"
    coverage: NonEmptyText
    status: Literal["restored", "failed", "unconfirmed"]
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)
    error: CleanupFailure | None = None

    @model_validator(mode="after")
    def error_matches_status(self) -> Self:
        if (self.status == "restored") == (self.error is not None):
            raise ValueError("Only unsuccessful checks require a cleanup diagnostic")
        return self


class RecoveryResult(Contract):
    """Backend facts; executor verifies binding, coverage and actual evidence."""

    schema_version: Literal["recovery-result/1"] = "recovery-result/1"
    allocation_id: Identifier
    actual_resource_id: Identifier
    checks: tuple[RecoveryCheck, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_checks(self) -> Self:
        if len({check.coverage for check in self.checks}) != len(self.checks):
            raise ValueError("Recovery coverage cannot be duplicated")
        return self


class RecoveryReceipt(Contract):
    schema_version: Literal["recovery-receipt/1"] = "recovery-receipt/1"
    intent: RecoveryIntent
    observation: RecoveryObservation
    result: RecoveryResult
    status: Literal["restored", "quarantined"]

    @model_validator(mode="after")
    def attribution(self) -> Self:
        token = self.intent.allocation
        if (
            self.observation.allocation_id != token.allocation_id
            or self.result.allocation_id != token.allocation_id
        ):
            raise ValueError("Recovery facts must identify the registered allocation")
        if (
            self.observation.actual_resource_id != token.expected_resource_id
            or self.result.actual_resource_id != token.expected_resource_id
        ):
            raise ValueError("Recovery cannot substitute another resource")
        complete = all(check.status == "restored" for check in self.result.checks)
        if (self.status == "restored") != complete:
            raise ValueError("Recovery status must retain unsuccessful checks")
        return self
