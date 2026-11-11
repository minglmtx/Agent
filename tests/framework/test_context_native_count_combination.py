"""Common preparation + original ActorService frames + closed read CAS audit.

Synthetic allowed source/authority and native tokenizer. No actual site/source
qualification, model inference, generic role fidelity or task/quality claim.
"""

import json
from lab_generate_skill.domain.context_transformation import (
    ContextTransformAudit,
    context_bytes_sha,
)
from pathlib import Path
from lab_generate_skill.application.context_preparation import (
    prepare_context,
    ContextPreparationDeps,
)
from lab_generate_skill.application.context_review import (
    review_context,
    ContextReviewDeps,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorMessage
from lab_generate_skill.domain.context_preparation import (
    ContextInputDraft,
    ContextPreparationRequest,
)
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ActorContextSource,
    ContextProjectionPolicy,
    ContextProtectionCheck,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from actor_context_fixtures import counter_case
from context_preparation_fixtures import UnitAuthority
from context_budget_fixtures import selection
from state_contract_fixtures import op
from test_actor_count_evidence import reviewer


class ModuleActorProjection:
    def project(
        self,
        source: AllowedContextSource,
        original: bytes,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextInputDraft, ...]:
        prompt = ActorPrompt(
            messages=(
                ActorMessage(role="system", content="unit-rules"),
                ActorMessage(role="user", content=json.loads(original)["body"]),
            )
        )
        return tuple(
            ContextInputDraft(
                candidate_id="native-" + str(i),
                kind=kind,
                source=source,
                policy_sha256=policy.digest,
                input_bytes=prompt.model_dump_json().encode(),
                audit=ContextTransformAudit(
                    role=source.role,
                    source_ref=source.original_ref,
                    policy_sha256=policy.digest,
                    kind=kind,
                    input_sha256=context_bytes_sha(prompt.model_dump_json().encode()),
                    no_op_reason="unit_unchanged",
                    changes=(),
                ),
            )
            for i, kind in enumerate(policy.candidate_order)
        )


class ModuleActorProtection:
    def verify(
        self,
        source: AllowedContextSource,
        original: bytes,
        draft: ContextInputDraft,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextProtectionCheck, ...]:
        actual = ActorPrompt.model_validate_json(draft.input_bytes)
        intact = (
            actual.messages[0].content == "unit-rules"
            and actual.messages[1].content == json.loads(original)["body"]
        )
        return tuple(
            ContextProtectionCheck(
                name=name,
                status="pass" if intact else "fail",
                reason_code="UNIT_COMPLETE_BODY",
            )
            for name in policy.protected_rules
        )


def test_native_count_CAS_preparation_then_closed_independent_count_audit(
    tmp_path: Path,
) -> None:
    case = counter_case(tmp_path)
    authority, projector, protection = (
        UnitAuthority(),
        ModuleActorProjection(),
        ModuleActorProtection(),
    )
    source = selection().candidates[0].source
    assert isinstance(source, ActorContextSource)
    original = case.evidence.put(
        b'{"body":"complete unit source"}',
        EvidenceMetadata(
            media_type="application/json",
            content_schema="actor-public-turn/1",
            visibility="public",
            producer="unit-allowed-source",
        ),
        case.control,
    )
    source = ActorContextSource.model_validate(
        {**source.model_dump(), "turn_ref": original}
    )
    request = ContextPreparationRequest(
        scope=source.scope,
        operation=op("native-context-module"),
        request_id="original-module-request",
        source=source,
        profile=case.profile,
        policy=case.policy,
    )
    prepared = prepare_context(
        request,
        ContextPreparationDeps(
            case.evidence, authority, projector, protection, case.counter
        ),
        control=case.control,
    )
    native_reviewer = reviewer(case)
    case.client.close(case.control)
    frames = len(case.channel.sent)
    receipt = review_context(
        request,
        prepared,
        ContextReviewDeps(
            case.evidence, authority, projector, protection, native_reviewer
        ),
        expected_input_ref=prepared.selected_input_ref,
        control=case.control,
    )
    assert receipt.outcome == "prepared" and len(receipt.counts) == 2
    assert all(c.measurement.input_tokens == 3 for c in receipt.counts)
    assert (
        len(case.channel.sent) == frames
        and case.loader.loads == case.loader.session.closed == 1
    )
    assert case.loader.session.calls == 0 and case.channel.finishes == 1
