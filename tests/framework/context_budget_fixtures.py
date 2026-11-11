"""Synthetic counts/validation refs, never real model or provider qualification."""

import hashlib
from typing import Any
from lab_generate_skill.domain.actor_projection import MapRailsDiagnosticProjection
from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    ContextRole,
    TokenMeasurement,
)
from lab_generate_skill.domain.context_projection import (
    ActorContextSource,
    TeacherContextSource,
    ContextProjectionPolicy,
    ContextSelection,
    MeasuredContextCandidate,
    ContextProtectionCheck,
    ProjectionKind,
)
from lab_generate_skill.domain.evidence import EvidenceRef, Visibility
from lab_generate_skill.domain.identity import TaskIdentity, Site
from state_contract_fixtures import scope


def ref(
    schema: str, visibility: Visibility = "private", tag: str = "unit"
) -> EvidenceRef:
    raw = (schema + ":" + tag).encode()
    digest = hashlib.sha256(raw).hexdigest()
    return EvidenceRef(
        uri="unit:" + digest,
        sha256=digest,
        size_bytes=len(raw),
        media_type="application/json",
        content_schema=schema,
        visibility=visibility,
        producer="unit-context",
    )


def profile(role: ContextRole = "actor", **changes: Any) -> ContextBudgetProfile:
    value = dict(
        role=role,
        model="unit-model",
        provider="unit-provider",
        routing_ref=ref("unit-routing/1"),
        configuration_ref=ref("model-parameters/1"),
        tokenizer_sha256="a" * 64,
        template_sha256="b" * 64,
        counting_method="unit-full-request-count",
        precision="exact",
        bound_evidence_ref=None,
        context_window=120,
        output_reserve=20,
        input_limit=100,
        provider_input_limit=None,
        soft_target=80,
        uncounted_overhead=0,
        paid=role == "teacher",
        fee_scope_ref=ref("budget-scope/1") if role == "teacher" else None,
    )
    return ContextBudgetProfile.model_validate({**value, **changes})


def selection(
    counts: tuple[int, ...] = (90, 70),
    *,
    role: ContextRole = "actor",
    site: Site = "map",
    kinds: tuple[ProjectionKind, ...] | None = None,
    configuration: ContextBudgetProfile | None = None,
    check_status: str = "pass",
    allow_fallback: bool = True,
    forced: ProjectionKind | None = None,
    structural: bool = False,
) -> ContextSelection:
    configuration = configuration if configuration is not None else profile(role)
    state = scope().model_copy(
        update={
            "task": TaskIdentity(
                task_id="unit-source",
                source_task_id="unit-source",
                site=site,
                family="unit-context-family",
                split="train",
                contract_version=1,
            )
        }
    )
    if structural:
        state = state.model_copy(
            update={
                "task": TaskIdentity(
                    task_id="b9101b71aacd51b61f6e",
                    source_task_id="b9101b71aacd51b61f6e",
                    site="map",
                    family="native_route_map_data",
                    split="train",
                    contract_version=1,
                )
            }
        )
    source = (
        ActorContextSource(
            scope=state,
            candidate_id="original-candidate",
            revision_round=0,
            turn_ref=ref("actor-public-turn/1", "public"),
        )
        if role == "actor"
        else TeacherContextSource(
            scope=state,
            teacher_round=1,
            allowed_input_ref=ref("teacher-input/1", "teacher"),
        )
    )
    defaults: tuple[ProjectionKind, ...] = (
        "identity",
        "exact_body_sharing",
        "structured_fields",
        "structural_ax",
    )
    order = kinds if kinds is not None else defaults[: len(counts)]
    policy = ContextProjectionPolicy(
        role=role,
        policy_id="unit-explicit",
        implementation_sha256="c" * 64,
        software_evidence_ref=ref("context-policy-evidence/1"),
        protected_rules=("scope", "relations"),
        candidate_order=order,
        allow_identity_fallback=allow_fallback,
        forced_kind=forced,
        actor_projection=MapRailsDiagnosticProjection() if structural else None,
    )
    candidates = []
    for i, (tokens, kind) in enumerate(zip(counts, order, strict=True)):
        measurement = TokenMeasurement(
            role=role,
            input_ref=ref(role + "-model-input/1", tag=str(i)),
            profile_sha256=configuration.digest,
            policy_sha256=policy.digest,
            input_tokens=tokens,
            upper_bound_tokens=tokens,
            precision="exact",
            complete_request=True,
            elapsed_seconds=0.0,
        )
        checks = tuple(
            ContextProtectionCheck.model_validate(
                dict(name=name, status=check_status, reason_code="UNIT_CHECK")
            )
            for name in policy.protected_rules
        )
        candidates.append(
            MeasuredContextCandidate(
                candidate_id="format-" + str(i),
                kind=kind,
                source=source,
                policy_sha256=policy.digest,
                measurement=measurement,
                checks=checks,
            )
        )
    return ContextSelection(
        profile=configuration, policy=policy, candidates=tuple(candidates)
    )
