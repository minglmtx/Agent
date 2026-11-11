"""Frozen per-task construction identities and append-only event payloads.

These private orchestration records never serve as Generator prompts. Pure
state projection is separate in construction_state.py; persistence and runtime
authority are ports. Evidence references describe facts, not their validity.
"""

from typing import Annotated, Literal, Self, Any

from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_versions import actor_version_fields, actor_version_output
from .state_scope import private_state_ref

from .construction_inputs import GeneratedCandidate, RevisionResult
from .construction_method import ConstructionMethod
from .evaluation import Evaluation
from .evidence import EvidenceRef
from .execution import AttemptBinding, RunBinding
from .lifecycle import OperationContext
from .errors import OwnershipConflict
from .retrieval import RetrievalScope
from .run_plan import ConstructionWorkload, RoleModelPlan, RunPlan
from .task import TaskBinding
from .validation import Contract, Identifier, Sha256

from .task_intent import TaskAttemptIntent

AttemptIntent = TaskAttemptIntent


class ConstructionPlan(Contract):
    schema_version: Literal["construction-plan/3", "construction-plan/4"] = (
        "construction-plan/3"
    )
    actor_context_configuration_ref: EvidenceRef | None = None
    run: RunBinding
    task: TaskBinding
    method: ConstructionMethod
    models: tuple[RoleModelPlan, ...]
    claim_ref: EvidenceRef
    public_context_ref: EvidenceRef
    context_receipt_ref: EvidenceRef
    retrieval_ref: EvidenceRef
    retrieval_scope: RetrievalScope
    max_actor_generations: int = Field(ge=1)
    max_interactions: int = Field(ge=1)

    @model_serializer(mode="wrap")
    def versioned_configuration(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.schema_version == "construction-plan/3",
            ("actor_context_configuration_ref",),
        )

    @model_validator(mode="after")
    def private_binding_public_context(self) -> Self:
        old = self.schema_version == "construction-plan/3"
        actor_version_fields(
            self,
            old,
            ("actor_context_configuration_ref",),
            record_name="Construction plan",
        )
        if old != (self.actor_context_configuration_ref is None):
            raise ValueError(
                "Plan4 requires explicit selected Actor context configuration; plan3 forbids it"
            )
        if self.actor_context_configuration_ref is not None:
            private_state_ref(
                self.actor_context_configuration_ref, "actor-context-configuration/1"
            )
        if self.task.identity.split != "train":
            raise ValueError("Target construction is train-only")
        if (
            self.public_context_ref.visibility != "public"
            or self.public_context_ref.content_schema != "public-construction-context/1"
        ):
            raise ValueError("Construction needs the frozen public context")
        if any(
            ref.visibility != "private"
            for ref in (self.claim_ref, self.context_receipt_ref, self.retrieval_ref)
        ):
            raise ValueError("Claim, qualification and retrieval lineage stay private")
        if (
            self.claim_ref.content_schema != "source-claim/1"
            or self.context_receipt_ref.content_schema != "public-context-receipt/1"
            or self.retrieval_ref.content_schema != "retrieval-result/1"
        ):
            raise ValueError(
                "Claim, context and retrieval require their versioned receipts"
            )
        if len(self.models) != 3 or {model.role for model in self.models} != {
            "actor",
            "generator",
            "teacher",
        }:
            raise ValueError("Construction requires exactly its three model roles")
        return self

    @classmethod
    def from_run_plan(
        cls,
        plan: RunPlan,
        run: RunBinding,
        task_id: str,
        *,
        claim_ref: EvidenceRef,
        public_context_ref: EvidenceRef,
        context_receipt_ref: EvidenceRef,
        retrieval_ref: EvidenceRef,
        retrieval_scope: RetrievalScope,
        actor_context_configuration_ref: EvidenceRef | None = None,
    ) -> "ConstructionPlan":
        plan = RunPlan.model_validate(plan)
        run = RunBinding.model_validate(run)
        plan.check_binding(run)
        if not isinstance(plan.workload, ConstructionWorkload):
            raise ValueError("Run workload is not target construction")
        retrieval_scope = RetrievalScope.model_validate(retrieval_scope)
        if (retrieval_scope.bank_ref, retrieval_scope.split_ref) != (
            plan.workload.bank_ref,
            plan.split_manifest_ref,
        ):
            raise OwnershipConflict(
                "Construction retrieval scope differs from frozen RunPlan"
            )
        tasks = [task for task in plan.tasks if task.identity.task_id == task_id]
        if len(tasks) != 1:
            raise ValueError("Construction task is not in the frozen run")
        selected: dict[str, Any] = (
            {}
            if actor_context_configuration_ref is None
            else dict(
                schema_version="construction-plan/4",
                actor_context_configuration_ref=actor_context_configuration_ref,
            )
        )
        return cls(
            **selected,
            run=run,
            task=tasks[0],
            method=plan.workload.method,
            models=plan.models,
            claim_ref=claim_ref,
            public_context_ref=public_context_ref,
            context_receipt_ref=context_receipt_ref,
            retrieval_ref=retrieval_ref,
            retrieval_scope=retrieval_scope,
            max_actor_generations=plan.resources.max_actor_generations_per_attempt,
            max_interactions=plan.resources.max_interactions_per_attempt,
        )


class ConstructionCall(Contract):
    """Register before invoking a model; not a RequestLedger dispatch permit."""

    schema_version: Literal["construction-call/1", "construction-call/2"] = (
        "construction-call/1"
    )
    request_id: Identifier
    role: Literal["generator", "teacher"]
    candidate_slot: int = Field(ge=0, le=6)
    resample_index: int = Field(ge=0, le=4)
    seed: int = Field(ge=0, le=2147483647)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    model_binding_ref: EvidenceRef
    base_parameters_ref: EvidenceRef
    input_ref: EvidenceRef
    parameters_ref: EvidenceRef

    @model_validator(mode="after")
    def role_input(self) -> Self:
        visibility, schema = (
            (
                "public",
                (
                    "generation-input/2"
                    if self.schema_version == "construction-call/2"
                    else "generation-input/1"
                ),
            )
            if self.role == "generator"
            else ("teacher", "revision-input/1")
        )
        if self.schema_version == "construction-call/2" and self.role != "generator":
            raise ValueError(
                "Call2 declares selected Generator capabilities; Teacher retains its own contract"
            )
        if (
            self.input_ref.visibility != visibility
            or self.input_ref.content_schema != schema
        ):
            raise ValueError("Call input must use its role's versioned allowed view")
        return self


class ConstructionAttemptResult(Contract):
    schema_version: Literal["construction-attempt-result/1"] = (
        "construction-attempt-result/1"
    )
    intent: AttemptIntent
    attempt_ref: EvidenceRef
    evaluation: Evaluation
    evaluation_ref: EvidenceRef
    interactions: int = Field(ge=0)
    generations: int = Field(ge=0)

    @model_validator(mode="after")
    def matching_judgment(self) -> Self:
        if self.intent.source_kind != "construction":
            raise ValueError("Construction result cannot relabel a single execution")
        if (
            self.evaluation.identity != self.intent.binding.task
            or self.evaluation.attempt_id != self.intent.binding.attempt_id
        ):
            raise ValueError("Evaluation must address this exact task attempt")
        if self.interactions > self.generations:
            raise ValueError("Environment returns cannot exceed model generations")
        if (
            self.evaluation_ref.content_schema != "evaluation/1"
            or self.evaluation_ref.visibility != "private"
            or self.attempt_ref.visibility != "private"
            or self.attempt_ref.content_schema != "attempt-result/1"
        ):
            raise ValueError(
                "Attempt and judgment evidence must retain private provenance"
            )
        return self


class SelectionResult(Contract):
    schema_version: Literal["construction-selection/1"] = "construction-selection/1"
    status: Literal["accepted", "rejected"]
    candidate_slot: int | None = Field(default=None, ge=0, le=6)
    attempt_id: Identifier | None = None
    skill_digest: Sha256 | None = None

    @model_validator(mode="after")
    def consistent_selection(self) -> Self:
        fields = (self.candidate_slot, self.attempt_id, self.skill_digest)
        if self.status == "accepted" and any(value is None for value in fields):
            raise ValueError("Accepted target needs its complete source binding")
        if self.status == "rejected" and any(value is not None for value in fields):
            raise ValueError("Rejected construction cannot publish a target")
        return self


class ConstructionEvent(Contract):
    schema_version: Literal["construction-event/1"] = "construction-event/1"
    operation: OperationContext


class CallPlanned(ConstructionEvent):
    kind: Literal["call_planned"] = "call_planned"
    call: ConstructionCall


class CallCompleted(ConstructionEvent):
    kind: Literal["call_completed"] = "call_completed"
    response: Annotated[
        GeneratedCandidate | RevisionResult, Field(discriminator="schema_version")
    ]


class CallUncertain(ConstructionEvent):
    kind: Literal["call_uncertain"] = "call_uncertain"
    request_id: Identifier
    evidence_ref: EvidenceRef


class AttemptPlanned(ConstructionEvent):
    kind: Literal["attempt_planned"] = "attempt_planned"
    intent: AttemptIntent

    @model_validator(mode="after")
    def construction_only(self) -> Self:
        if self.intent.source_kind != "construction":
            raise ValueError("Construction journal cannot register an execution intent")
        return self


class AttemptCompleted(ConstructionEvent):
    kind: Literal["attempt_completed"] = "attempt_completed"
    result: ConstructionAttemptResult


class AttemptResolved(ConstructionEvent):
    """Replace only an unknown judgment using explicit supersedes, not execution."""

    kind: Literal["attempt_resolved"] = "attempt_resolved"
    result: ConstructionAttemptResult


class SelectionCommitted(ConstructionEvent):
    kind: Literal["selection_committed"] = "selection_committed"
    selection: SelectionResult


ProgressEvent = Annotated[
    CallPlanned
    | CallCompleted
    | CallUncertain
    | AttemptPlanned
    | AttemptCompleted
    | AttemptResolved
    | SelectionCommitted,
    Field(discriminator="kind"),
]
