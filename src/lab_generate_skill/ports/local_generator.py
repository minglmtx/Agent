"""Runtime engine, real admission and recovery interfaces for local inference.

Engine has no implicit retries or hidden truncation. Runtime owns model lease,
fixed local artifacts and external process supervision. validate must not infer.
Authority must check actual pending construction intent, claim/writer/release,
complete original model/base/actual parameters and qualified public projection.
Completion reconciliation verifies actual original provenance, not just hashes.
No test implementation may become a production default.
"""

from typing import Protocol
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBinding,
    LocalGeneratorIntent,
    LocalGeneratorParameters,
    LocalGeneratorOutput,
    LocalGeneratorSnapshot,
    LocalGeneratorFact,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl


class LocalGeneratorEngine(Protocol):
    def validate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None: ...
    def generate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput: ...


class GeneratorInvocationEngine(Protocol):
    """Called only after original intent first commits under the durable lock.

    Owns no retry/admission policy. Must retain the actual exchange bound to
    this intent before returning; unresolved invocations cannot be sent again.
    """

    def validate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None: ...
    def invoke(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput: ...


class ManagedLocalGeneratorEngine(LocalGeneratorEngine, Protocol):
    """Worker-owned engine; explicit close is required for service shutdown."""

    def close(self, control: OperationControl) -> None: ...


class LocalGeneratorAuthority(Protocol):
    def authorize_access(
        self,
        binding: LocalGeneratorBinding,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
    def authorize_generate(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None: ...
    def verify_completion(
        self,
        fact: LocalGeneratorFact,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...


class GeneratorInferenceRecovery(Protocol):
    def inspect(
        self, request: GeneratorModelRequest, op: OperationContext
    ) -> LocalGeneratorSnapshot: ...
    def reconcile(
        self,
        request: GeneratorModelRequest,
        fact_ref: EvidenceRef,
        op: OperationContext,
    ) -> EvidenceRef: ...
