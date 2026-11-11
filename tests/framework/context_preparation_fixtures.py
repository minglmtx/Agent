"""Synthetic allowed sources/count evidence for common I/O tests only.

Not real Actor/Teacher layouts, tokenizers, source admission or site fidelity.
Native Actor count evidence has its separate real service/closed-read module.
"""

import json
from lab_generate_skill.domain.context_transformation import (
    ContextTransformAudit,
    context_bytes_sha,
)
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.application.context_preparation import ContextPreparationDeps
from lab_generate_skill.application.context_review import ContextReviewDeps
from lab_generate_skill.domain.context_preparation import (
    ContextPreparationRequest,
    ContextInputDraft,
)
from lab_generate_skill.domain.context_budget import (
    ContextRole,
    ContextBudgetProfile,
    TokenMeasurement,
    CountedContextInput,
)
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ActorContextSource,
    TeacherContextSource,
    ContextProjectionPolicy,
    ContextProtectionCheck,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata, Visibility
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.ports.lifecycle import OperationControl
from context_budget_fixtures import selection
from evidence_control_fixtures import EvidenceFixtureStore
from state_contract_fixtures import op


class UnitAuthority:
    pending = False
    calls = 0
    reviews = 0

    def verify_prepare(
        self, request: ContextPreparationRequest, *, control: OperationControl
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if self.pending:
            raise PermissionError(
                "original request is unknown; new ID/format grants nothing"
            )

    def verify_recorded(
        self,
        request: ContextPreparationRequest,
        reference: EvidenceRef,
        *,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.reviews += 1


class UnitProjection:
    def project(
        self,
        source: AllowedContextSource,
        original: bytes,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextInputDraft, ...]:
        body = json.loads(original)["body"]
        raw = json.dumps(
            {"schema_version": source.role + "-model-input/1", "body": body},
            separators=(",", ":"),
        ).encode()
        return tuple(
            ContextInputDraft(
                candidate_id="format-" + str(i),
                kind=kind,
                source=source,
                policy_sha256=policy.digest,
                input_bytes=raw,
                audit=ContextTransformAudit(
                    role=source.role,
                    source_ref=source.original_ref,
                    policy_sha256=policy.digest,
                    kind=kind,
                    input_sha256=context_bytes_sha(raw),
                    no_op_reason="unit_unchanged",
                    changes=(),
                ),
            )
            for i, kind in enumerate(policy.candidate_order)
        )


class UnitProtection:
    status: str = "pass"

    def verify(
        self,
        source: AllowedContextSource,
        original: bytes,
        draft: ContextInputDraft,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextProtectionCheck, ...]:
        value = json.loads(draft.input_bytes)
        valid = (
            value["body"] == json.loads(original)["body"]
            and value["schema_version"] == source.role + "-model-input/1"
        )
        return tuple(
            ContextProtectionCheck.model_validate(
                dict(
                    name=name,
                    status=self.status if valid else "fail",
                    reason_code="UNIT_FIELDS",
                )
            )
            for name in policy.protected_rules
        )


class UnitCounts:
    def __init__(self, evidence: EvidenceFixtureStore) -> None:
        self.evidence = evidence
        self.calls = self.reviews = 0

    def measure(
        self,
        input_ref: EvidenceRef,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> CountedContextInput:
        control.checkpoint()
        self.calls += 1
        tokens = len(json.loads(self.evidence.read(input_ref, control))["body"]) + 1
        measurement = TokenMeasurement(
            role=profile.role,
            input_ref=input_ref,
            profile_sha256=profile.digest,
            policy_sha256=policy.digest,
            input_tokens=tokens,
            upper_bound_tokens=tokens,
            precision="exact",
            complete_request=True,
            elapsed_seconds=0.0,
        )
        raw = json.dumps(
            {
                "input": input_ref.sha256,
                "tokens": tokens,
                "profile": profile.digest,
                "policy": policy.digest,
            },
            separators=(",", ":"),
        ).encode()
        proof = self.evidence.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=profile.role + "-context-count-execution/1",
                visibility="private",
                producer="unit-count-only",
            ),
            control,
        )
        return CountedContextInput(measurement=measurement, evidence_ref=proof)

    def verify(
        self,
        counted: CountedContextInput,
        profile: ContextBudgetProfile,
        policy: ContextProjectionPolicy,
        *,
        control: OperationControl,
    ) -> TokenMeasurement:
        control.checkpoint()
        self.reviews += 1
        proof = json.loads(self.evidence.read(counted.evidence_ref, control))
        measurement = counted.measurement
        actual = (
            len(json.loads(self.evidence.read(measurement.input_ref, control))["body"])
            + 1
        )
        if (
            proof
            != dict(
                input=measurement.input_ref.sha256,
                tokens=actual,
                profile=profile.digest,
                policy=policy.digest,
            )
            or measurement.input_tokens != actual
        ):
            raise ValueError("unit count proof mismatch")
        return measurement


@dataclass
class PreparationCase:
    request: ContextPreparationRequest
    evidence: EvidenceFixtureStore
    authority: UnitAuthority
    projector: UnitProjection
    protection: UnitProtection
    counter: UnitCounts

    def deps(self) -> ContextPreparationDeps:
        return ContextPreparationDeps(
            self.evidence, self.authority, self.projector, self.protection, self.counter
        )

    def review_deps(self) -> ContextReviewDeps:
        return ContextReviewDeps(
            self.evidence, self.authority, self.projector, self.protection, self.counter
        )


def preparation_case(
    root: Path,
    role: ContextRole = "actor",
    site: Site = "map",
    *,
    tokens: int = 3,
    two_formats: bool = False,
) -> PreparationCase:
    root.mkdir(exist_ok=True)
    evidence = EvidenceFixtureStore(root)
    sample = selection(
        role=role,
        site=site,
        counts=(tokens, tokens) if two_formats else (tokens,),
        kinds=("identity", "exact_body_sharing") if two_formats else ("identity",),
    )
    source = sample.candidates[0].source
    visibility: Visibility = "public" if role == "actor" else "teacher"
    raw = json.dumps({"body": "x" * (tokens - 1)}).encode()
    reference = evidence.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema=(
                "actor-public-turn/1" if role == "actor" else "teacher-input/1"
            ),
            visibility=visibility,
            producer="unit-context-source",
        ),
    )
    if isinstance(source, ActorContextSource):
        source = ActorContextSource.model_validate(
            {**source.model_dump(), "turn_ref": reference}
        )
    else:
        source = TeacherContextSource.model_validate(
            {**source.model_dump(), "allowed_input_ref": reference}
        )
    request = ContextPreparationRequest(
        scope=source.scope,
        operation=op("context-prepare"),
        request_id="original-request",
        source=source,
        profile=sample.profile,
        policy=sample.policy,
    )
    return PreparationCase(
        request,
        evidence,
        UnitAuthority(),
        UnitProjection(),
        UnitProtection(),
        UnitCounts(evidence),
    )
