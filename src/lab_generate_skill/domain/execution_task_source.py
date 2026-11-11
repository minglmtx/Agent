"""Frozen original single-execution inputs; no construction events or permission."""

import hashlib
from typing import Any, Literal, Self
from dataclasses import dataclass
from .run_plan import RunPlan, ExecutionWorkload
from .source_actor_policy import EngineeringActorPolicy
from .public_context import PublicContextReceipt
from pydantic import model_validator, model_serializer, SerializerFunctionWrapHandler
from .validation import Contract, Identifier
from .evidence import EvidenceRef
from .execution import RunBinding
from .task import TaskBinding, PublicTask
from .errors import OwnershipConflict
from .task_intent import TaskAttemptIntent
from .state_scope import private_state_ref
from .claims import SourceClaimBinding
from .lifecycle import ResourceOwner
from .frozen_execution_origin import FrozenExecutionOrigin


class ExecutionTaskInputs(Contract):
    schema_version: Literal["execution-task-inputs/1"] = "execution-task-inputs/1"
    task_binding_ref: EvidenceRef
    source_context_receipt_ref: EvidenceRef
    skill_ref: EvidenceRef
    attempt_id: Identifier

    @model_validator(mode="after")
    def original_inputs(self) -> Self:
        private_state_ref(self.task_binding_ref, "task-binding/1")
        private_state_ref(self.source_context_receipt_ref, "public-context-receipt/1")
        if (self.skill_ref.visibility, self.skill_ref.content_schema) != (
            "public",
            "compact-skill/1",
        ):
            raise ValueError("Explicit original allowed execution skill required")
        return self


class ExecutionTaskSource(Contract):
    schema_version: Literal["execution-task-source/1", "execution-task-source/2"] = (
        "execution-task-source/1"
    )
    run: RunBinding
    task: TaskBinding
    intent: TaskAttemptIntent
    source_context_receipt_ref: EvidenceRef
    frozen_origin: FrozenExecutionOrigin | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.schema_version == "execution-task-source/1":
            value.pop("frozen_origin", None)
        return value

    @model_validator(mode="after")
    def original_source(self) -> Self:
        if self.schema_version == "execution-task-source/1":
            if "frozen_origin" in self.model_fields_set:
                raise ValueError("Original source forbids a frozen-validation field")
        else:
            if self.frozen_origin is None:
                raise ValueError("Source2 requires an explicit frozen origin")
            validation = self.frozen_origin.validation
            validation.require_current_binding(
                SourceClaimBinding(
                    scope_id=validation.parent.record.binding.scope_id,
                    run=self.run,
                    task=self.task,
                )
            )
        private_state_ref(self.source_context_receipt_ref, "public-context-receipt/1")
        if (
            self.intent.source_kind != "execution"
            or self.intent.binding.run != self.run
            or self.intent.binding.task != self.task.identity
        ):
            raise ValueError("Single source changed its original run/task/intent")
        return self


@dataclass(frozen=True)
class ExecutionSourceFacts:
    source: ExecutionTaskSource
    inputs: ExecutionTaskInputs
    run: RunPlan
    policy: EngineeringActorPolicy
    context: PublicContextReceipt


from .claims import SourceClaimReceipt


@dataclass(frozen=True)
class ClaimedExecutionSourceFacts(ExecutionSourceFacts):
    """One installed proof's immutable claim body; never current permission."""

    claim: SourceClaimReceipt


def execution_context_owner(
    source: ExecutionTaskSource, parent_source: ExecutionTaskSource | None
) -> ResourceOwner:
    """Verify the original manifest without changing its owner or qualification."""
    origin = source.frozen_origin
    if origin is None:
        if parent_source is not None:
            raise OwnershipConflict("Ordinary source cannot inherit a parent")
        return source.run.owner
    parent = origin.validation.parent
    if (
        parent_source is None
        or parent_source.schema_version != "execution-task-source/1"
    ):
        raise OwnershipConflict("Frozen validation requires its original source body")
    raw = parent_source.model_dump_json().encode()
    if (
        origin.parent_source_ref.sha256 != hashlib.sha256(raw).hexdigest()
        or origin.parent_source_ref.size_bytes != len(raw)
        or parent_source.run != parent.record.binding.run
        or parent_source.task != parent.record.binding.task
        or parent_source.task != source.task
        or parent_source.intent.binding.claim_ref != parent.reference
        or parent_source.source_context_receipt_ref != source.source_context_receipt_ref
        or parent_source.intent.public_context_ref != source.intent.public_context_ref
    ):
        raise OwnershipConflict("Frozen source differs from exact parent claim/context")
    return parent_source.run.owner


def check_execution_source_facts(
    source: ExecutionTaskSource,
    inputs: ExecutionTaskInputs,
    run: RunPlan,
    policy: EngineeringActorPolicy,
    binding: TaskBinding,
    public: "PublicTask",
    context: PublicContextReceipt,
    skill: bytes,
    *,
    parent_source: ExecutionTaskSource | None = None,
) -> ExecutionSourceFacts:
    """Original immutable comparisons shared by parent and fixed readonly proof.

    This grants nothing: the caller separately requires the durable original
    claim and current resource/storage authority on every invocation.
    """
    context_owner = execution_context_owner(source, parent_source)
    workload = run.workload
    if (
        not isinstance(workload, ExecutionWorkload)
        or run.purpose != "engineering"
        or run.split != "train"
        or run.tasks != (source.task,)
        or len(run.models) != 1
        or run.models[0].role != "actor"
        or run.models[0].paid
    ):
        raise OwnershipConflict(
            "Current single engineering scope is train/actor-only/unpaid"
        )
    if (
        workload.execution_policy_ref != source.intent.execution_policy_ref
        or workload.task_inputs_ref != source.intent.execution_inputs_ref
    ):
        raise OwnershipConflict("Execution policy/inputs changed original RunPlan")
    if (
        inputs.attempt_id != source.intent.binding.attempt_id
        or binding != source.task
        or inputs.source_context_receipt_ref != source.source_context_receipt_ref
        or policy.skill.content_digest != source.intent.skill_digest
        or policy.max_generations != run.resources.max_actor_generations_per_attempt
        or policy.max_interactions != run.resources.max_interactions_per_attempt
        or policy.memory != run.policies.actor_memory
        or context.scope.task != binding.identity
        or context.scope.owner != context_owner
        or context.scope.attempt_id == source.intent.binding.attempt_id
        or context.spec_ref != binding.baseline_ref
        or context.public_context_ref != source.intent.public_context_ref
    ):
        raise OwnershipConflict(
            "Execution changed exact policy/private task/source qualification"
        )
    if (
        skill != policy.skill.model_dump_json().encode()
        or public.identity != binding.identity
    ):
        raise OwnershipConflict("Execution changed explicit skill/public task bytes")
    return ExecutionSourceFacts(source, inputs, run, policy, context)
