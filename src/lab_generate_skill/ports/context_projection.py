"""Controlled full-request counting; implementations confer no dispatch rights."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    CountedContextInput,
    TokenMeasurement,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from .lifecycle import OperationControl
from .evidence import EvidenceReader, EvidenceStore
from lab_generate_skill.domain.context_preparation import (
    ContextPreparationRequest,
    ContextInputDraft,
)
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ContextProtectionCheck,
)


class ContextTokenCounter(Protocol):
    def measure(
        self,
        input_ref: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> CountedContextInput:
        """Count complete final input/template; preserve precision and frozen identities.

        Original model adapters keep their final token and fee gates. Count/save
        failure must leave the original logical request unsubmitted.
        """
        ...


class ContextPreparationAuthority(Protocol):
    def verify_prepare(
        self, request: ContextPreparationRequest, *, control: OperationControl
    ) -> None:
        """Original source/allowed evidence/frozen pins; pending unknown refuses.

        No default implementation or grant follows from preparation metadata.
        """
        ...

    def verify_recorded(
        self,
        request: ContextPreparationRequest,
        reference: EvidenceRef,
        *,
        control: OperationControl,
    ) -> None:
        """Historical provenance without requiring still-live resources."""
        ...


class ContextInputProjector(Protocol):
    def project(
        self,
        source: AllowedContextSource,
        original: bytes,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextInputDraft, ...]:
        """Pure deterministic complete input rendering from allowed role data."""
        ...


class ContextProtectionVerifier(Protocol):
    def verify(
        self,
        source: AllowedContextSource,
        original: bytes,
        draft: ContextInputDraft,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextProtectionCheck, ...]:
        """Pure independent field/relationship extraction, no I/O."""
        ...


class ContextCountEvidenceVerifier(Protocol):
    def verify(
        self,
        counted: CountedContextInput,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> TokenMeasurement:
        """Verify original count facts without repeating external invocation."""
        ...


@runtime_checkable
class ContextCountInputReview(Protocol):
    def with_inputs(self, evidence: "EvidenceReader") -> ContextCountEvidenceVerifier:
        """Use exact same-call bodies; repeat the full original count verification."""
        ...


@runtime_checkable
class ContextTokenInputMeasure(Protocol):
    def with_inputs(self, evidence: EvidenceStore) -> ContextTokenCounter:
        """Use same confirmed bodies and original writes; keep native count live."""
        ...


@runtime_checkable
class ContextTokenReturnMeasure(Protocol):
    def measure_with_return(
        self,
        input_ref: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
        retention_control: OperationControl,
    ) -> CountedContextInput:
        """Count once under execution; retain the actual reply under original cleanup."""
        ...
