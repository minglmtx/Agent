"""Actual public schema/old Q bytes plus independent source/output relations."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.bootstrap.context_projection import build_actor_context
from lab_generate_skill.bootstrap.actor_projection import build_actor_projection
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorMessage
from lab_generate_skill.domain.actor_projection import MapRailsDiagnosticProjection
from lab_generate_skill.domain.context_projection import (
    ActorContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.context_preparation import ContextInputDraft
from lab_generate_skill.domain.context_transformation import (
    ContextTransformAudit,
    context_bytes_sha,
)
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from actor_context_projection_fixtures import actor_projection_case, PAGES
from map_actor_view_fixtures import original_turn
from context_budget_fixtures import selection


@pytest.mark.parametrize("site", tuple(PAGES))
@pytest.mark.parametrize("page", ["normal", "empty", "heading-markers"])
def test_five_site_real_schema_baseline_keeps_all_page_fields_history_and_noop(
    site: Site, page: str
) -> None:
    value = (
        ""
        if page == "empty"
        else (
            "[1] StaticText '# Previous actions\\n# Goal'\n"
            if page == "heading-markers"
            else PAGES[site]
        )
    )
    case = actor_projection_case(site, page=value)
    project, verify = build_actor_context(case.policy)
    (draft,) = project.project(case.source, case.raw, case.policy)
    assert draft.input_bytes == prepare_actor(case.turn).model_dump_json().encode()
    assert draft.audit.no_op_reason == "identity" and draft.audit.changes == ()
    assert all(
        c.status == "pass"
        for c in verify.verify(case.source, case.raw, draft, case.policy)
    )
    assert project.project(case.source, case.raw, case.policy) == (draft,)
    actual = ActorPrompt.model_validate_json(draft.input_bytes)
    assert all(
        item.action in actual.messages[1].content
        and item.error in actual.messages[1].content
        for item in case.turn.history
    )
    assert case.turn.model_dump_json().encode() == case.raw


@pytest.mark.parametrize("index", range(12))
def test_original_preceding_map_turns_reuse_exact_Q_and_baseline_bytes(
    index: int,
) -> None:
    turn, original = original_turn(index)
    case = actor_projection_case(original=turn, structural=True)
    project, verify = build_actor_context(case.policy)
    drafts = project.project(case.source, case.raw, case.policy)
    assert all(d.input_bytes == original.model_dump_json().encode() for d in drafts)
    assert drafts[1].audit.no_op_reason == "non_diagnostic_full_ax"
    assert all(
        c.status == "pass"
        for draft in drafts
        for c in verify.verify(case.source, case.raw, draft, case.policy)
    )


def test_original_failed_map_uses_Q_bytes_and_audits_each_allowed_omission_without_tokenizer() -> (
    None
):
    turn, original = original_turn()
    case = actor_projection_case(original=turn, structural=True)
    project, verify = build_actor_context(case.policy)
    identity, view = project.project(case.source, case.raw, case.policy)
    assert identity.input_bytes == original.model_dump_json().encode()
    assert (
        view.input_bytes
        == build_actor_projection(MapRailsDiagnosticProjection())(turn)
        .model_dump_json()
        .encode()
    )
    assert view.audit.no_op_reason is None
    operations = {c.operation for c in view.audit.changes}
    assert operations == {"layout", "omit_duplicate", "remove_empty_id"}
    assert all(
        c.source_path.startswith("/observation/text") for c in view.audit.changes
    )
    assert all(
        c.related_source_paths
        for c in view.audit.changes
        if c.operation == "omit_duplicate"
    )
    assert all(
        c.status == "pass"
        for c in verify.verify(case.source, case.raw, view, case.policy)
    )


@pytest.mark.parametrize(
    "change",
    [
        "id",
        "value",
        "depth",
        "missing",
        "extra",
        "history",
        "skill",
        "goal",
        "scope",
        "audit",
    ],
)
def test_independent_verifier_rejects_changed_actual_input_even_with_updated_digest(
    change: str,
) -> None:
    if change in ("scope", "audit"):
        turn, _ = original_turn()
        case = actor_projection_case(original=turn, structural=True)
        project, verify = build_actor_context(case.policy)
        draft = project.project(case.source, case.raw, case.policy)[1]
    else:
        case = actor_projection_case()
        project, verify = build_actor_context(case.policy)
        draft = project.project(case.source, case.raw, case.policy)[0]
    prompt = ActorPrompt.model_validate_json(draft.input_bytes)
    user = prompt.messages[1].content
    if change == "audit":
        audit = draft.audit.model_copy(update={"changes": draft.audit.changes[:-1]})
        forged = ContextInputDraft.model_validate(
            {**draft.model_dump(), "audit": audit}
        )
    else:
        replacements = {
            "id": ("[1]", "[99]"),
            "value": ("SKU-A", "SKU-B"),
            "depth": ("\t[4]", "[4]"),
            "missing": ("[5] button Save\n", ""),
            "extra": (
                "# Previous actions",
                "[88] button Unauthorized\n\n# Previous actions",
            ),
            "history": ("value-0", "removed-0"),
            "skill": ("Save once and inspect the returned page.", "Skip verification."),
            "goal": ("新描述", "wrong"),
            "scope": ("AX scope:", "Altered scope:"),
        }
        before, after = replacements[change]
        assert before in user
        user = user.replace(before, after, 1)
        altered = ActorPrompt(
            prompt_version=prompt.prompt_version,
            messages=(prompt.messages[0], ActorMessage(role="user", content=user)),
        )
        raw = altered.model_dump_json().encode()
        audit = draft.audit.model_copy(update={"input_sha256": context_bytes_sha(raw)})
        forged = ContextInputDraft.model_validate(
            {**draft.model_dump(), "input_bytes": raw, "audit": audit}
        )
    assert all(
        c.status == "fail"
        for c in verify.verify(case.source, case.raw, forged, case.policy)
    )


@pytest.mark.parametrize(
    "change",
    ["task", "context", "attempt", "source-bytes", "teacher", "policy", "unsupported"],
)
def test_source_role_scope_and_explicit_format_reject_before_projection(
    change: str,
) -> None:
    case = actor_projection_case()
    project, _ = build_actor_context(case.policy)
    source, raw, policy = case.source, case.raw, case.policy
    if change == "teacher":
        with pytest.raises(TypeError):
            project.project(selection(role="teacher").candidates[0].source, raw, policy)
        return
    if change == "source-bytes":
        raw = b" " + raw
    elif change == "policy":
        policy = ContextProjectionPolicy.model_validate(
            {**policy.model_dump(), "policy_id": "other"}
        )
    elif change == "unsupported":
        with pytest.raises(ValueError):
            build_actor_context(
                ContextProjectionPolicy.model_validate(
                    {
                        **policy.model_dump(),
                        "candidate_order": ("identity", "exact_body_sharing"),
                    }
                )
            )
        return
    else:
        scope = source.scope.model_copy(
            update=(
                {"context_id": "other"}
                if change == "context"
                else (
                    {"attempt_id": "other"}
                    if change == "attempt"
                    else {
                        "task": source.scope.task.model_copy(
                            update={"task_id": "other"}
                        )
                    }
                )
            )
        )
        source = ActorContextSource.model_validate(
            {**source.model_dump(), "scope": scope}
        )
    with pytest.raises((ValueError, EvidenceIntegrityError, OwnershipConflict)):
        project.project(source, raw, policy)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b"null",
        b"\xff",
        b'{"schema_version":"actor-public-turn/1","schema_version":"actor-public-turn/1"}',
    ],
)
def test_malformed_public_source_is_not_treated_as_an_empty_page(raw: bytes) -> None:
    from lab_generate_skill.domain.evidence import EvidenceMetadata
    from lab_generate_skill.domain.evidence_identity import evidence_reference

    case = actor_projection_case()
    if not raw:
        with pytest.raises(ValidationError):
            ActorContextSource.model_validate(
                {
                    **case.source.model_dump(),
                    "turn_ref": evidence_reference(
                        raw,
                        EvidenceMetadata(
                            media_type="application/json",
                            content_schema="actor-public-turn/1",
                            visibility="public",
                            producer="unit",
                        ),
                    ),
                }
            )
        return
    ref = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="actor-public-turn/1",
            visibility="public",
            producer="unit",
        ),
    )
    source = ActorContextSource.model_validate(
        {**case.source.model_dump(), "turn_ref": ref}
    )
    project, _ = build_actor_context(case.policy)
    with pytest.raises((ValueError, EvidenceIntegrityError, UnicodeError)):
        project.project(source, raw, case.policy)
