"""Explicit original construction preparation commands and saved step binding."""

from typing import Literal, Self
import hashlib
from pydantic import Field, model_validator
from .validation import Contract, Identifier
from .execution import RunBinding
from .lifecycle import OperationContext
from .construction_control import ConstructionStepPlan
from .construction_inputs import PublicConstructionContext
from .evidence import EvidenceRef
from .local_generator import LocalGeneratorBaseParameters
from .skill import CompactSkill
from .generator_actor_capabilities import GeneratorActorCapabilities
from .state_scope import private_state_ref
from .model_request import check_model_cleanup


class GeneratorPreparation(Contract):
    schema_version: Literal["construction-generation-preparation/1"] = (
        "construction-generation-preparation/1"
    )
    run: RunBinding
    expected_revision: int = Field(ge=-1, le=255)
    request_id: Identifier
    operation: OperationContext
    invoke_operation: OperationContext
    completion_operation: OperationContext

    @model_validator(mode="after")
    def original_operations(self) -> Self:
        owner = self.run.owner
        for op in (self.operation, self.invoke_operation, self.completion_operation):
            if (
                op.run_id,
                op.owner_id,
                op.attempt_id,
                op.allocation_id,
                op.recovery_ref,
            ) != (owner.run_id, owner.owner_id, None, None, None):
                raise ValueError(
                    "Generator preparation requires original run-level operations"
                )
        if self.operation.mode != "execute" or self.invoke_operation.mode != "execute":
            raise ValueError("Cleanup cannot prepare or invoke new Generator work")
        if self.completion_operation.mode == "cleanup":
            check_model_cleanup(self.invoke_operation, self.completion_operation)
        if (
            len(
                {
                    self.operation.operation_id,
                    self.invoke_operation.operation_id,
                    self.completion_operation.operation_id,
                }
            )
            != 3
        ):
            raise ValueError(
                "Original registration/invocation/completion identities must differ"
            )
        if len(self.model_dump_json().encode()) > 32768:
            raise ValueError("Preparation command exceeds bounded metadata")
        return self


class ConstructionGenerationSource(Contract):
    context: PublicConstructionContext
    skills: tuple[CompactSkill, ...] = Field(min_length=6, max_length=6)
    base: LocalGeneratorBaseParameters
    actor_capabilities: GeneratorActorCapabilities | None = None


class PublishedConstructionStep(Contract):
    schema_version: Literal["published-construction-step/1"] = (
        "published-construction-step/1"
    )
    reference: EvidenceRef
    step: ConstructionStepPlan

    @model_validator(mode="after")
    def private_complete_step(self) -> Self:
        private_state_ref(self.reference, "construction-step-plan/1")
        if (
            self.reference.media_type != "application/json"
            or not 0 < self.reference.size_bytes <= 4 * 1024**2
        ):
            raise ValueError("Complete bounded private construction step required")
        raw = self.step.model_dump_json().encode()
        if (self.reference.sha256, self.reference.size_bytes) != (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
        ):
            raise ValueError(
                "Saved construction step must bind its exact canonical bytes"
            )
        return self
