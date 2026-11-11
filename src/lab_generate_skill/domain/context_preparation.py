"""Input preparation facts; none authorize model or website requests."""

from typing import Annotated, ClassVar, Literal, Self
from pydantic import Field, model_validator
from .context_budget import ContextBudgetProfile, CountedContextInput
from .adaptive_candidates import adaptive_candidate_ids
from .context_projection import (
    AllowedContextSource,
    ContextProjectionPolicy,
    ContextProtectionCheck,
    ContextSelection,
    ContextDecision,
    ProjectionKind,
)
from .state_scope import StateScope, private_state_ref
from .teacher_scope import TeacherContextScope
from .lifecycle import OperationContext
from .errors import OwnershipConflict
from .validation import Contract, Identifier, Sha256
from .evidence import EvidenceRef
from .context_transformation import ContextTransformAudit, context_bytes_sha
from .actor_projection import AdaptiveObservationProjection

PreparationOutcome = Literal["prepared", "integrity_rejected", "budget_rejected"]


class ContextPreparationRequest(Contract):
    operation_mode: ClassVar[Literal["execute"]] = "execute"
    scope: Annotated[
        StateScope | TeacherContextScope, Field(discriminator="schema_version")
    ]
    operation: OperationContext
    schema_version: Literal[
        "context-preparation-request/1", "context-preparation-request/2"
    ] = "context-preparation-request/1"
    request_id: Identifier
    source: AllowedContextSource
    profile: ContextBudgetProfile
    policy: ContextProjectionPolicy

    @model_validator(mode="after")
    def original_role_and_scope(self) -> Self:
        task_level = isinstance(self.scope, TeacherContextScope)
        if task_level != (self.schema_version == "context-preparation-request/2"):
            raise ValueError(
                "Teacher task scope requires explicit preparation v2; v1 preserves original Actor layout"
            )
        expected_attempt = (
            self.scope.attempt_id if isinstance(self.scope, StateScope) else None
        )
        if (
            self.operation.run_id,
            self.operation.owner_id,
            self.operation.attempt_id,
            self.operation.mode,
        ) != (
            self.scope.owner.run_id,
            self.scope.owner.owner_id,
            expected_attempt,
            "execute",
        ):
            raise OwnershipConflict(
                "Context preparation must retain original run/owner/role scope and execute phase"
            )
        if task_level and (
            self.source.role != "teacher"
            or self.operation.allocation_id is not None
            or self.operation.recovery_ref is not None
        ):
            raise OwnershipConflict(
                "Task-level Teacher cannot borrow an Actor attempt/allocation/recovery"
            )
        if (
            self.scope != self.source.scope
            or self.source.role != self.profile.role
            or self.profile.role != self.policy.role
        ):
            raise ValueError(
                "Preparation requires original allowed role/scope/profile/policy"
            )
        return self


class ContextInputDraft(Contract):
    """Only rendered allowed input bytes; no private dependency container."""

    candidate_id: Identifier
    kind: ProjectionKind
    source: AllowedContextSource
    policy_sha256: Sha256
    input_bytes: bytes = Field(min_length=1, max_length=64 * 1024**2)
    audit: ContextTransformAudit

    @model_validator(mode="after")
    def bounded_role_bytes(self) -> Self:
        if self.source.role == "actor" and len(self.input_bytes) > 8 * 1024**2:
            raise ValueError("Actor complete input exceeds byte boundary")
        if (
            self.audit.role,
            self.audit.source_ref,
            self.audit.policy_sha256,
            self.audit.kind,
            self.audit.input_sha256,
        ) != (
            self.source.role,
            self.source.original_ref,
            self.policy_sha256,
            self.kind,
            context_bytes_sha(self.input_bytes),
        ):
            raise ValueError(
                "Transformation audit changed original source/policy/kind/input"
            )
        return self


class ContextDraftRecord(Contract):
    candidate_id: Identifier
    kind: ProjectionKind
    input_ref: EvidenceRef
    audit_ref: EvidenceRef
    checks: tuple[ContextProtectionCheck, ...] = Field(min_length=1, max_length=64)


class ContextPreparationReceipt(Contract):
    schema_version: Literal["context-preparation/2"] = "context-preparation/2"
    request: ContextPreparationRequest
    outcome: PreparationOutcome
    drafts: tuple[ContextDraftRecord, ...] = Field(min_length=1, max_length=4)
    counts: tuple[CountedContextInput, ...] = Field(max_length=4)
    selection: ContextSelection | None
    decision: ContextDecision | None

    @model_validator(mode="after")
    def complete_preparation_facts(self) -> Self:
        request = self.request
        adaptive = isinstance(
            request.policy.actor_projection, AdaptiveObservationProjection
        )
        formats = tuple(d.kind for d in self.drafts)
        expected: tuple[tuple[str, ...], ...] = (
            (("local_ax",),)
            if getattr(request.source, "active_read_ref", None) is not None
            else (("compact_full_ax",), ("compact_full_ax", "local_ax"))
        )
        if adaptive and request.policy.schema_version == "context-projection-policy/3":
            expected += (("compact_full_ax", "local_ax", "local_ax"),)
            ids = tuple(draft.candidate_id for draft in self.drafts)
            declared = adaptive_candidate_ids(
                request.policy.schema_version,
                active_read=getattr(request.source, "active_read_ref", None)
                is not None,
            )
            if ids != declared[: len(ids)]:
                raise ValueError(
                    "Recorded adaptive candidates changed frozen identity/order"
                )
        if (
            (adaptive and formats not in expected)
            or (not adaptive and formats != request.policy.candidate_order)
        ) or len({d.candidate_id for d in self.drafts}) != len(self.drafts):
            raise ValueError("All frozen candidates required in declared order")
        valid = True
        for draft in self.drafts:
            private_state_ref(
                draft.audit_ref,
                (
                    "context-transform-audit/2"
                    if adaptive
                    else "context-transform-audit/1"
                ),
            )
            if (
                draft.audit_ref.media_type != "application/json"
                or not 0 < draft.audit_ref.size_bytes <= 64 * 1024**2
            ):
                raise ValueError("Complete transformation audit reference required")
            if {c.name for c in draft.checks} != set(
                request.policy.protected_rules
            ) or len({c.name for c in draft.checks}) != len(draft.checks):
                raise ValueError("Each frozen protection rule requires one check")
            if (
                draft.input_ref.visibility,
                draft.input_ref.content_schema,
                draft.input_ref.media_type,
            ) != (
                "private",
                request.source.role + "-model-input/1",
                "application/json",
            ) or not 0 < draft.input_ref.size_bytes <= (
                8 if request.source.role == "actor" else 64
            ) * 1024**2:
                raise ValueError("Complete bounded role input references required")
            valid = valid and all(c.status == "pass" for c in draft.checks)
        if self.outcome == "integrity_rejected":
            if (
                valid
                or self.selection is not None
                or self.decision is not None
                or (not adaptive and self.counts)
                or (adaptive and len(self.counts) != len(self.drafts) - 1)
            ):
                raise ValueError("Integrity refusal precedes counting and selection")
            if adaptive:
                for draft, counted in zip(self.drafts[:-1], self.counts, strict=True):
                    if not all(check.status == "pass" for check in draft.checks) or (
                        counted.measurement.input_ref,
                        counted.measurement.profile_sha256,
                        counted.measurement.policy_sha256,
                    ) != (
                        draft.input_ref,
                        request.profile.digest,
                        request.policy.digest,
                    ):
                        raise ValueError(
                            "Preserved earlier counts changed original protected adaptive prefix"
                        )
        else:
            if (
                not valid
                or self.selection is None
                or self.decision is None
                or len(self.counts) != len(self.drafts)
            ):
                raise ValueError(
                    "Budget preparation requires complete protected count facts"
                )
            selection, decision = self.selection, self.decision
            if (
                selection.profile != request.profile
                or selection.policy != request.policy
                or decision.selection_sha256 != selection.digest
                or decision.source != request.source
                or decision.profile_sha256 != request.profile.digest
                or decision.policy_sha256 != request.policy.digest
            ):
                raise ValueError("Selection/decision changed original request bindings")
            for draft, counted, candidate in zip(
                self.drafts, self.counts, selection.candidates, strict=True
            ):
                if (
                    candidate.source != request.source
                    or (
                        candidate.candidate_id,
                        candidate.kind,
                        candidate.measurement,
                        candidate.checks,
                    )
                    != (
                        draft.candidate_id,
                        draft.kind,
                        counted.measurement,
                        draft.checks,
                    )
                    or counted.measurement.input_ref != draft.input_ref
                ):
                    raise ValueError("Candidate/count facts differ from full inputs")
            if decision.accepted != (self.outcome == "prepared"):
                raise ValueError("Outcome and actual budget decision disagree")
        if len(self.model_dump_json().encode()) > 256 * 1024:
            raise ValueError("Preparation metadata exceeds small-object boundary")
        return self


class PreparedContextRef(Contract):
    """Saved outcome, never an inference send permit."""

    schema_version: Literal["prepared-context-ref/2"] = "prepared-context-ref/2"
    request_sha256: Sha256
    reference: EvidenceRef
    outcome: PreparationOutcome
    selected_input_ref: EvidenceRef | None

    @model_validator(mode="after")
    def saved_result(self) -> Self:
        private_state_ref(self.reference, "context-preparation/2")
        if (
            self.reference.media_type != "application/json"
            or not 0 < self.reference.size_bytes <= 256 * 1024
        ):
            raise ValueError("Original bounded preparation reference required")
        if (self.selected_input_ref is not None) != (self.outcome == "prepared"):
            raise ValueError("Only accepted preparation supplies a selected input")
        return self
