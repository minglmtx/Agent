"""Role-separated allowed-source references and finite protected context candidates."""

import hashlib
from typing import Annotated, Literal, Self, Any
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from .actor_versions import actor_version_fields, actor_version_output
from .adaptive_candidates import ADAPTIVE_POLICY_SCHEMAS, adaptive_candidate_ids
from .actor_projection import (
    ActorProjectionConfiguration,
    MapRailsDiagnosticProjection,
    MapRailsAddressableProjection,
    check_projection_task,
    AdaptiveObservationProjection,
)
from .context_budget import ContextBudgetProfile, ContextRole, TokenMeasurement
from .evidence import EvidenceRef
from .state_scope import StateScope
from .teacher_scope import TeacherContextScope
from .validation import Contract, Identifier, Sha256

ProjectionKind = Literal[
    "identity",
    "structured_fields",
    "exact_body_sharing",
    "structural_ax",
    "compact_full_ax",
    "local_ax",
]


class ActorContextSource(Contract):
    role: Literal["actor"] = "actor"
    scope: StateScope
    candidate_id: Identifier
    revision_round: int = Field(ge=0, le=3)
    turn_ref: EvidenceRef
    active_read_ref: EvidenceRef | None = None

    @model_serializer(mode="wrap")
    def original_wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return actor_version_output(
            self,
            handler,
            self.turn_ref.content_schema == "actor-public-turn/1",
            ("active_read_ref",),
        )

    @property
    def original_ref(self) -> EvidenceRef:
        return self.turn_ref

    @model_validator(mode="after")
    def public_turn(self) -> Self:
        old = self.turn_ref.content_schema == "actor-public-turn/1"
        actor_version_fields(
            self, old, ("active_read_ref",), record_name="Actor context source"
        )
        if (
            self.turn_ref.content_schema
            not in ("actor-public-turn/1", "actor-public-turn/2")
            or self.turn_ref.visibility != "public"
        ):
            raise ValueError("Actor context only accepts the original public turn")
        if (
            self.turn_ref.media_type != "application/json"
            or not 0 < self.turn_ref.size_bytes <= 8 * 1024**2
        ):
            raise ValueError("Complete bounded Actor turn JSON required")
        if self.active_read_ref is not None and (
            self.active_read_ref.visibility != "public"
            or self.active_read_ref.content_schema != "observation-read-result/2"
        ):
            raise ValueError("Actual active read reference must be public result v2")
        return self


class TeacherContextSource(Contract):
    role: Literal["teacher"] = "teacher"
    scope: Annotated[
        StateScope | TeacherContextScope, Field(discriminator="schema_version")
    ]
    teacher_round: int = Field(ge=1, le=3)
    allowed_input_ref: EvidenceRef

    @property
    def original_ref(self) -> EvidenceRef:
        return self.allowed_input_ref

    @model_validator(mode="after")
    def permitted_input(self) -> Self:
        if (
            self.allowed_input_ref.content_schema != "teacher-input/1"
            or self.allowed_input_ref.visibility != "teacher"
        ):
            raise ValueError(
                "Teacher context only accepts its original permitted projection"
            )
        if (
            self.allowed_input_ref.media_type != "application/json"
            or not 0 < self.allowed_input_ref.size_bytes <= 64 * 1024**2
        ):
            raise ValueError("Complete bounded permitted Teacher JSON required")
        return self


AllowedContextSource = Annotated[
    ActorContextSource | TeacherContextSource, Field(discriminator="role")
]


class ContextProjectionPolicy(Contract):
    schema_version: Literal[
        "context-projection-policy/1",
        "context-projection-policy/2",
        "context-projection-policy/3",
    ] = "context-projection-policy/1"
    role: ContextRole
    policy_id: Identifier
    implementation_sha256: Sha256
    software_evidence_ref: EvidenceRef
    protected_rules: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    candidate_order: tuple[ProjectionKind, ...] = Field(min_length=1, max_length=4)
    allow_identity_fallback: bool
    forced_kind: ProjectionKind | None
    actor_projection: ActorProjectionConfiguration | None

    @model_validator(mode="after")
    def explicit_order_and_role(self) -> Self:
        if len(set(self.protected_rules)) != len(self.protected_rules) or len(
            set(self.candidate_order)
        ) != len(self.candidate_order):
            raise ValueError("Unique protection rules and candidate formats required")
        adaptive = isinstance(self.actor_projection, AdaptiveObservationProjection)
        if adaptive != (self.schema_version in ADAPTIVE_POLICY_SCHEMAS):
            raise ValueError("Adaptive Actor strategy requires explicit policy v2")
        if adaptive:
            if (
                self.role != "actor"
                or self.candidate_order != ("compact_full_ax", "local_ax")
                or self.forced_kind is not None
            ):
                raise ValueError(
                    "Adaptive policy has exactly two ordered Actor modes and no forced bypass"
                )
        elif any(
            kind in ("compact_full_ax", "local_ax") for kind in self.candidate_order
        ):
            raise ValueError(
                "Original context policy cannot declare unregistered adaptive modes"
            )
        if (not adaptive and self.candidate_order[0] != "identity") or (
            self.forced_kind is not None
            and self.forced_kind not in self.candidate_order
        ):
            raise ValueError(
                "Original candidate first and any forced format explicitly declared"
            )
        if self.software_evidence_ref.visibility != "private":
            raise ValueError("Original strategy validation evidence must be private")
        if self.role == "teacher" and (
            self.actor_projection is not None or "structural_ax" in self.candidate_order
        ):
            raise ValueError(
                "Teacher cannot inherit an Actor structure/content projection"
            )
        if "structural_ax" in self.candidate_order and self.actor_projection is None:
            raise ValueError(
                "Actor structure candidate needs an explicit validated projection selection"
            )
        if "structural_ax" in self.candidate_order and not isinstance(
            self.actor_projection,
            (MapRailsDiagnosticProjection, MapRailsAddressableProjection),
        ):
            raise ValueError(
                "Only the explicitly validated Map structure projection is currently declared"
            )
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class ContextProtectionCheck(Contract):
    name: Identifier
    status: Literal["pass", "fail", "unknown"]
    reason_code: Identifier


class MeasuredContextCandidate(Contract):
    candidate_id: Identifier
    kind: ProjectionKind
    source: AllowedContextSource
    policy_sha256: Sha256
    measurement: TokenMeasurement
    checks: tuple[ContextProtectionCheck, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def coherent_role_checks(self) -> Self:
        if self.source.role != self.measurement.role or len(
            {c.name for c in self.checks}
        ) != len(self.checks):
            raise ValueError("Candidate role and unique protected relations required")
        if self.source.role == "teacher" and self.kind == "structural_ax":
            raise ValueError(
                "Teacher full original bodies cannot use Actor AX reduction"
            )
        return self


class ContextSelection(Contract):
    schema_version: Literal["context-selection/1", "context-selection/2"] = (
        "context-selection/1"
    )
    profile: ContextBudgetProfile
    policy: ContextProjectionPolicy
    candidates: tuple[MeasuredContextCandidate, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def original_finite_bindings(self) -> Self:
        adaptive = isinstance(
            self.policy.actor_projection, AdaptiveObservationProjection
        )
        if adaptive != (self.schema_version == "context-selection/2"):
            raise ValueError("Adaptive evaluation order requires explicit selection v2")
        kinds = tuple(c.kind for c in self.candidates)
        source = self.candidates[0].source
        if adaptive:
            assert isinstance(
                self.policy.actor_projection, AdaptiveObservationProjection
            )
            if (
                not isinstance(source, ActorContextSource)
                or source.turn_ref.content_schema != "actor-public-turn/2"
            ):
                raise ValueError(
                    "Adaptive selection requires its exact complete public turn2"
                )
            allowed: tuple[tuple[str, ...], ...] = (
                (("local_ax",),)
                if source.active_read_ref is not None
                else (("compact_full_ax",), ("compact_full_ax", "local_ax"))
            )
            if self.policy.schema_version == "context-projection-policy/3":
                expected_ids = adaptive_candidate_ids(
                    self.policy.schema_version,
                    active_read=source.active_read_ref is not None,
                )
                actual_ids = tuple(
                    candidate.candidate_id for candidate in self.candidates
                )
                if actual_ids != expected_ids[: len(actual_ids)]:
                    raise ValueError(
                        "Adaptive navigation candidates changed frozen identity/order"
                    )
                allowed += (("compact_full_ax", "local_ax", "local_ax"),)
            if (
                kinds not in allowed
                or self.profile.soft_target
                != self.policy.actor_projection.read_policy.switch_tokens
            ):
                raise ValueError(
                    "Adaptive evaluated formats or frozen soft threshold changed"
                )
        if self.profile.role != self.policy.role or (
            not adaptive and kinds != self.policy.candidate_order
        ):
            raise ValueError("Exact frozen role and candidate order required")
        if len({c.candidate_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate context candidate identity")
        original = self.candidates[0].source
        for c in self.candidates:
            if (
                c.source != original
                or c.source.role != self.profile.role
                or c.policy_sha256 != self.policy.digest
            ):
                raise ValueError(
                    "Context candidate changed original source/task/round/policy"
                )
            if (
                c.measurement.profile_sha256 != self.profile.digest
                or c.measurement.precision != self.profile.precision
                or c.measurement.policy_sha256 != self.policy.digest
            ):
                raise ValueError(
                    "Context measurement changed frozen model/routing/template/counting profile"
                )
            if {x.name for x in c.checks} != set(self.policy.protected_rules):
                raise ValueError("Every declared protected relation must be checked")
        if self.policy.actor_projection is not None:
            check_projection_task(self.policy.actor_projection, original.scope.task)
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class ContextCandidateAssessment(Contract):
    candidate_id: Identifier
    input_ref: EvidenceRef
    input_tokens: int = Field(ge=1)
    budget_tokens: int = Field(ge=1)
    integrity: Literal["pass", "fail", "unknown"]
    within_soft: bool
    within_hard: bool

    @model_validator(mode="after")
    def coherent_bound(self) -> Self:
        if self.budget_tokens < self.input_tokens or (
            self.within_soft and not self.within_hard
        ):
            raise ValueError(
                "Assessment needs a conservative count and coherent soft/hard limits"
            )
        return self


class ContextDecision(Contract):
    schema_version: Literal[
        "context-budget-decision/1", "context-budget-decision/2"
    ] = "context-budget-decision/1"
    source: AllowedContextSource
    profile_sha256: Sha256
    policy_sha256: Sha256
    selection_sha256: Sha256
    accepted: bool
    reason_code: Literal[
        "below_soft_identity",
        "shorter_verified_candidate",
        "explicit_format",
        "identity_fallback",
        "input_budget_exceeded",
        "integrity_rejected",
        "no_permitted_candidate",
        "adaptive_compact_full",
        "adaptive_local",
        "adaptive_complete_required",
    ]
    selected_candidate_id: Identifier | None
    selected_input_ref: EvidenceRef | None
    assessments: tuple[ContextCandidateAssessment, ...] = Field(
        min_length=1, max_length=4
    )

    @model_validator(mode="after")
    def selection_is_preparation_only(self) -> Self:
        accepted_reasons = (
            "below_soft_identity",
            "shorter_verified_candidate",
            "explicit_format",
            "identity_fallback",
            "adaptive_compact_full",
            "adaptive_local",
            "adaptive_complete_required",
        )
        adaptive = self.schema_version == "context-budget-decision/2"
        if (
            self.reason_code
            in ("adaptive_compact_full", "adaptive_local", "adaptive_complete_required")
        ) and not adaptive:
            raise ValueError(
                "Original decision cannot silently claim adaptive mode selection"
            )
        if adaptive and (
            not isinstance(self.source, ActorContextSource)
            or self.source.turn_ref.content_schema != "actor-public-turn/2"
        ):
            raise ValueError("Adaptive budget decision needs original public turn2")
        if self.accepted != (self.reason_code in accepted_reasons) or len(
            {a.candidate_id for a in self.assessments}
        ) != len(self.assessments):
            raise ValueError(
                "Decision outcome/reason and candidate identities must agree"
            )
        if any(
            a.input_ref.content_schema != self.source.role + "-model-input/1"
            or a.input_ref.visibility != "private"
            for a in self.assessments
        ):
            raise ValueError("Decision cannot change role or input visibility")
        if self.accepted != (
            self.selected_candidate_id is not None
            and self.selected_input_ref is not None
        ):
            raise ValueError(
                "Accepted context requires its exact selected input reference"
            )
        if not self.accepted and (
            self.selected_candidate_id is not None
            or self.selected_input_ref is not None
        ):
            raise ValueError("Rejected context cannot retain a selected send input")
        if self.accepted and not any(
            a.candidate_id == self.selected_candidate_id
            and a.input_ref == self.selected_input_ref
            and a.integrity == "pass"
            and a.within_hard
            for a in self.assessments
        ):
            raise ValueError(
                "Selected input must have complete protection and hard-budget checks"
            )
        return self
