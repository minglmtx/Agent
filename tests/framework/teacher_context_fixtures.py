"""Synthetic complete permitted evidence, full native fields and fake counts.

No real source admission, Teacher provider/tokenizer/credit or model request.
The unit byte-token engine below counts a complete synthetic wire, not a claim
about OpenRouter. Production must supply its own frozen credible count proof.
"""

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
from pydantic import JsonValue
from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    TeacherChatMessage,
)
from lab_generate_skill.domain.teacher_json import json_text, json_value
from lab_generate_skill.domain.context_projection import (
    TeacherContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.context_budget import (
    ContextBudgetProfile,
    CountedContextInput,
    TokenMeasurement,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.context_preparation import ContextPreparationRequest
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.application.context_preparation import ContextPreparationDeps
from lab_generate_skill.application.context_review import ContextReviewDeps
from lab_generate_skill.bootstrap.context_projection import build_teacher_context
from lab_generate_skill.teacher.context_source import TEACHER_PROTECTION_RULES
from lab_generate_skill.teacher.context_projection import TeacherContextProjector
from lab_generate_skill.teacher.context_protection import TeacherContextProtection
from evidence_control_fixtures import EvidenceFixtureStore
from context_preparation_fixtures import UnitAuthority
from context_budget_fixtures import profile, selection
from actor_context_projection_fixtures import PAGES
from state_contract_fixtures import scope, op
from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from test_actor_protocol import turn


@dataclass(frozen=True)
class TeacherProjectionCase:
    allowed: AllowedTeacherEvidence
    source: TeacherContextSource
    raw: bytes
    policy: ContextProjectionPolicy


def teacher_projection_case(
    site: Site = "map", *, repeated_page_bytes: int = 0
) -> TeacherProjectionCase:
    task = turn().task
    task = task.model_copy(
        update={"identity": task.identity.model_copy(update={"site": site})}
    )
    state = TeacherContextScope(
        owner=scope().owner, task=task.identity, context_id=scope().context_id
    )
    page = PAGES[site] + (
        "\n[900] text " + "精确完整正文\u00a0\tλ[]\n" * repeated_page_bytes
        if repeated_page_bytes
        else ""
    )
    attempts: list[JsonValue] = []
    for i, status in enumerate(("failure", "unknown", "success")):
        messages: list[JsonValue] = []
        for j in range(9):
            body: dict[str, JsonValue] = dict(
                goal=task.goal,
                axtree_txt=page,
                axtree_full_txt=page + "\ncomplete supplemental original page",
                url=f"https://{site}.example/objects/{i}",
                open_tabs=[{"title": "Same title", "url": f"/candidate/{i}"}],
                active_tab_index=0,
                observation_scope="original_public",
                observation_mode="complete",
                observation_policy={"version": 1},
                last_action_error=f"original step {j}: unsaved/rejected",
                actor_visible_input={
                    "format": "actor-original-or-structure",
                    "text": page[:40],
                    "stage": "before_actual_generation",
                },
                numeric=[1, 1.0, True, "€12.30", "42 ms"],
                unknown_tree={"children": [{"id": 1}, {"id": 2}]},
            )
            if j == 8:
                body["observation_record_source"] = "later_terminal_capture"
                body.pop("actor_visible_input")
            messages.append(
                dict(
                    role="user",
                    content=json_text(body),
                    turn=len(messages),
                    action_kind=None,
                    action_payload=None,
                )
            )
            if j == 8:
                continue
            m: dict[str, JsonValue] = dict(
                role="assistant",
                content=f"complete proposal {j} click('999') is only text",
                turn=len(messages),
                operation_result={
                    "status": "unknown" if j == 0 else "failed",
                    "error": "original error",
                    "result": None,
                },
            )
            payloads: list[JsonValue] = [
                None,
                "",
                "  ",
                "click('1')",
                [],
                {"unknown": "shape"},
                False,
            ]
            if j:
                m["action_payload"] = payloads[j - 1]
            if j % 2:
                m["action_kind"] = None
            messages.append(m)
        messages.append(
            dict(
                role="tool",
                content=None,
                missing_output={"reason": "unavailable"},
                turn=True,
            )
        )
        attempts.append(
            dict(
                candidate_id="candidate-" + str(i),
                attempt_id="attempt-" + str(i),
                revision_round=i,
                status=status,
                skill=json_value(turn().skill.model_payload()),
                trajectory=messages,
                feedback={
                    "scope": "overall_task",
                    "status": status,
                    "no_per_tool_inference": True,
                },
                unknown_candidate_field={"keep": [0, False, None]},
            )
        )
    evidence: dict[str, JsonValue] = dict(
        task=task.goal,
        initial_observation=page,
        public_task=task.model_dump(mode="json"),
        retrieved_skills=[json_value(turn().skill.model_payload())] * 6,
        attempts=attempts,
        revision_request={"round": 3, "retain_all_attempts": True},
    )
    allowed = AllowedTeacherEvidence(
        scope=state,
        task=task,
        teacher_round=3,
        messages=(
            TeacherChatMessage(
                role="system",
                content="Original Teacher instructions/constraints/skill schema.\n",
            ),
            TeacherChatMessage(role="user", content=json_text(evidence)),
        ),
    )
    raw = allowed.model_dump_json().encode()
    reference = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-input/1",
            visibility="teacher",
            producer="unit-approved-teacher-only",
        ),
    )
    source = TeacherContextSource(
        scope=state, teacher_round=3, allowed_input_ref=reference
    )
    base = selection(
        role="teacher", kinds=("identity", "exact_body_sharing"), counts=(90, 70)
    ).policy
    policy = ContextProjectionPolicy.model_validate(
        {**base.model_dump(), "protected_rules": TEACHER_PROTECTION_RULES}
    )
    return TeacherProjectionCase(allowed, source, raw, policy)


def synthetic_wire(raw: bytes, model: str) -> bytes:
    return json.dumps(
        dict(
            template="unit-byte-token-chat/1",
            model=model,
            input=json.loads(raw),
            parameters={
                "max_tokens": 17,
                "reasoning": "unit_reserved_in_17",
                "response_format": {"type": "unit_complete_skill_schema"},
            },
            provider={"unit_no_fallback": True},
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


class UnitTeacherCountReview:
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store
        self.reviews = 0

    def wire(self, raw: bytes, model: str) -> bytes:
        return synthetic_wire(raw, model)

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
        measurement = counted.measurement
        wire = self.wire(self.store.read(measurement.input_ref, control), profile.model)
        proof = json.loads(self.store.read(counted.evidence_ref, control))
        if (
            proof
            != dict(
                synthetic=True,
                wire_sha256=hashlib.sha256(wire).hexdigest(),
                measurement=measurement.model_dump(mode="json"),
            )
            or measurement.input_tokens != len(wire)
            or measurement.upper_bound_tokens != len(wire)
            or measurement.profile_sha256 != profile.digest
            or measurement.policy_sha256 != policy.digest
        ):
            raise ValueError("Original unit complete-wire count proof changed")
        return measurement


class UnitTeacherCounts(UnitTeacherCountReview):
    def __init__(self, store: EvidenceFixtureStore) -> None:
        super().__init__(store)
        self.writer = store
        self.calls = 0
        self.fail_after: int | None = None

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
        if self.fail_after == self.calls:
            raise TimeoutError("original unit count operation stopped")
        wire = self.wire(self.store.read(input_ref, control), profile.model)
        count = len(wire)
        measurement = TokenMeasurement(
            role="teacher",
            input_ref=input_ref,
            profile_sha256=profile.digest,
            policy_sha256=policy.digest,
            input_tokens=count,
            upper_bound_tokens=count,
            precision="exact",
            complete_request=True,
            elapsed_seconds=0.0,
        )
        proof = json.dumps(
            dict(
                synthetic=True,
                wire_sha256=hashlib.sha256(wire).hexdigest(),
                measurement=measurement.model_dump(mode="json"),
            ),
            separators=(",", ":"),
        ).encode()
        ref = self.writer.put(
            proof,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="teacher-context-count-execution/1",
                visibility="private",
                producer="unit-byte-token-engine",
            ),
            control,
        )
        return CountedContextInput(measurement=measurement, evidence_ref=ref)


@dataclass
class TeacherPreparationCase:
    original: TeacherProjectionCase
    request: ContextPreparationRequest
    store: EvidenceFixtureStore
    authority: UnitAuthority
    project: TeacherContextProjector
    protect: TeacherContextProtection
    counter: UnitTeacherCounts

    def deps(self) -> ContextPreparationDeps:
        return ContextPreparationDeps(
            self.store, self.authority, self.project, self.protect, self.counter
        )

    def review_deps(self) -> ContextReviewDeps:
        return ContextReviewDeps(
            self.store, self.authority, self.project, self.protect, self.counter
        )


def teacher_preparation_case(
    root: Path,
    site: Site = "map",
    *,
    repeated_page_bytes: int = 0,
    limit: int = 100000,
    soft: int = 85000,
) -> TeacherPreparationCase:
    root.mkdir(exist_ok=True)
    original = teacher_projection_case(site, repeated_page_bytes=repeated_page_bytes)
    store = EvidenceFixtureStore(root)
    reference = store.put(
        original.raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-input/1",
            visibility="teacher",
            producer="unit-approved-teacher-only",
        ),
    )
    assert reference == original.source.allowed_input_ref
    budget = profile(
        "teacher",
        model="unit-teacher-byte-tokens",
        context_window=limit + 17,
        input_limit=limit,
        output_reserve=17,
        soft_target=soft,
        counting_method="unit-byte-token-chat-v1",
    )
    request = ContextPreparationRequest(
        schema_version="context-preparation-request/2",
        scope=original.source.scope,
        operation=op("teacher-original-request").model_copy(
            update={"attempt_id": None}
        ),
        request_id="teacher-3-original",
        source=original.source,
        profile=budget,
        policy=original.policy,
    )
    project, protect = build_teacher_context(original.policy)
    return TeacherPreparationCase(
        original,
        request,
        store,
        UnitAuthority(),
        project,
        protect,
        UnitTeacherCounts(store),
    )
