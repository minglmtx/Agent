"""Private admission request/facts and a public projection handoff, not a permit."""

from typing import Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_inputs import ActorInput
from .baseline import BaselineReceipt
from .task_intent import TaskAttemptIntent as AttemptIntent
from .construction_inputs import PublicConstructionContext
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .execution import AttemptBinding
from .initial_equivalence import EquivalenceReceipt
from .lifecycle import OperationContext
from .observation import ResolvedObservation
from .public_context import PublicContextReceipt
from .skill import CompactSkill
from .state_scope import private_state_ref
from .task import TaskBinding
from .validation import Contract


class ActorAdmissionRequest(Contract):
    schema_version: Literal["actor-admission-request/1"] = "actor-admission-request/1"
    intent: AttemptIntent
    equivalence_ref: EvidenceRef
    skill_ref: EvidenceRef
    operation: OperationContext
    read_operation: OperationContext

    @model_validator(mode="after")
    def attempt_command_and_independent_read(self) -> Self:
        if self.intent.source_kind != "construction":
            raise ValueError(
                "Construction candidate admission requires construction intent"
            )
        private_state_ref(self.equivalence_ref, "equivalence-receipt/1")
        if (self.skill_ref.visibility, self.skill_ref.content_schema) != (
            "public",
            "compact-skill/1",
        ):
            raise ValueError(
                "Actor admission requires the exact public candidate skill"
            )
        binding = self.intent.binding
        owner = binding.run.owner
        op, read = self.operation, self.read_operation
        if (op.run_id, op.owner_id, op.attempt_id, op.mode) != (
            owner.run_id,
            owner.owner_id,
            binding.attempt_id,
            "execute",
        ):
            raise OwnershipConflict(
                "Actor admission requires its attempt execute operation"
            )
        if (read.run_id, read.owner_id, read.attempt_id) != (
            owner.run_id,
            owner.owner_id,
            None,
        ) or read.operation_id == op.operation_id:
            raise OwnershipConflict(
                "Journal read needs an independent original run-level operation"
            )
        return self


class CandidateFacts(Contract):
    schema_version: Literal["candidate-facts/1"] = "candidate-facts/1"
    equivalence_ref: EvidenceRef
    skill_ref: EvidenceRef
    equivalence: EquivalenceReceipt
    source: PublicContextReceipt
    context: PublicConstructionContext
    baseline: BaselineReceipt
    task_binding: TaskBinding
    observation: ResolvedObservation
    skill: CompactSkill


class PreparedActorInput(Contract):
    """Only actor_input may enter the role. Revisions require CAS before execution."""

    schema_version: Literal["prepared-actor-input/1", "prepared-actor-input/2"] = (
        "prepared-actor-input/1"
    )
    binding: AttemptBinding
    operation: OperationContext
    equivalence_ref: EvidenceRef
    baseline_ref: EvidenceRef
    run_revision: int = Field(ge=0)
    construction_revision: int | None = Field(default=None, ge=0)
    actor_input: ActorInput
    execution_source_ref: EvidenceRef | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.schema_version == "prepared-actor-input/1":
            data.pop("execution_source_ref", None)
        else:
            data.pop("construction_revision", None)
        return data

    @model_validator(mode="after")
    def actual_source_kind(self) -> Self:
        if self.schema_version == "prepared-actor-input/1":
            if (
                self.construction_revision is None
                or "execution_source_ref" in self.model_fields_set
            ):
                raise ValueError(
                    "Original candidate admission requires actual construction revision"
                )
        else:
            if (
                self.execution_source_ref is None
                or "construction_revision" in self.model_fields_set
            ):
                raise ValueError(
                    "Execution input requires genuine execution source, no construction history"
                )
            if self.execution_source_ref.content_schema not in (
                "execution-task-source/1",
                "execution-task-source/2",
            ):
                raise ValueError("Unsupported explicit Actor execution source version")
            private_state_ref(
                self.execution_source_ref, self.execution_source_ref.content_schema
            )
        return self
