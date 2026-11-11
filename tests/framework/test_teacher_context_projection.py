"""Full real Teacher formats with synthetic allowed sources; no model effects."""

import json
from pathlib import Path
from typing import Any, Callable, cast
from dataclasses import replace
import pytest
from pydantic import JsonValue, ValidationError
from lab_generate_skill.bootstrap.context_projection import build_teacher_context
from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    TeacherModelInput,
    native_evidence,
)
from lab_generate_skill.domain.teacher_projection import (
    TeacherProjectionPayload,
    TEACHER_VIEW_VERSION,
)
from lab_generate_skill.domain.teacher_json import json_text, read_json
from lab_generate_skill.domain.context_projection import (
    ActorContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.context_preparation import ContextInputDraft
from lab_generate_skill.domain.context_transformation import context_bytes_sha
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.teacher.context_protection import teacher_audit
from teacher_context_fixtures import teacher_projection_case, TeacherProjectionCase
from actor_context_projection_fixtures import actor_projection_case


def actual_payload(draft: ContextInputDraft) -> TeacherProjectionPayload:
    return TeacherProjectionPayload.model_validate_json(
        TeacherModelInput.model_validate_json(draft.input_bytes).messages[1].content
    )


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_full_allowed_source_original_pair_and_independent_complete_page_event_audit(
    site: Site,
) -> None:
    c = teacher_projection_case(site)
    project, protect = build_teacher_context(c.policy)
    drafts = project.project(c.source, c.raw, c.policy)
    assert tuple(d.kind for d in drafts) == ("identity", "exact_body_sharing")
    original = TeacherModelInput.model_validate_json(drafts[0].input_bytes)
    assert original.messages == c.allowed.messages and not drafts[0].audit.changes
    payload = actual_payload(drafts[1])
    assert (
        payload.version == TEACHER_VIEW_VERSION and not payload.archival_byte_reversible
    )
    assert len(payload.pages) == 2
    attempts = payload.evidence["attempts"]
    assert isinstance(attempts, list) and len(attempts) == 3
    first = attempts[0]
    assert isinstance(first, dict) and first["candidate_id"] == "candidate-0"
    events = first["events"]
    assert isinstance(events, list) and len(events) > 6
    actions = [
        e["recorded_action"]
        for e in events
        if isinstance(e, dict) and e["kind"] == "actor_response"
    ]
    assert [a["state"] for a in actions if isinstance(a, dict)] == [
        "missing",
        "null",
        "empty",
        "empty",
        "nonempty",
        "unrecognized_type",
        "unrecognized_type",
        "unrecognized_type",
    ]
    assert any(x.operation == "share_exact_body" for x in drafts[1].audit.changes)
    assert any(x.operation == "omit_duplicate" for x in drafts[1].audit.changes)
    assert all(
        all(
            check.status == "pass"
            for check in protect.verify(c.source, c.raw, d, c.policy)
        )
        for d in drafts
    )
    assert set(json.loads(drafts[1].input_bytes)) == {"messages"}
    assert c.raw == c.allowed.model_dump_json().encode()


def test_native_golden_core_projection_migrates_without_importing_historical_runtime() -> (
    None
):
    from lab_generate_skill import teacher_evidence_projection as old

    legacy: Callable[
        [dict[str, JsonValue]], tuple[dict[str, JsonValue], dict[str, JsonValue]]
    ] = cast(
        Callable[
            [dict[str, JsonValue]], tuple[dict[str, JsonValue], dict[str, JsonValue]]
        ],
        old.project,
    )
    c = teacher_projection_case("gitlab")
    drafts = build_teacher_context(c.policy)[0].project(c.source, c.raw, c.policy)
    expected, _ = legacy(native_evidence(c.allowed.messages[1].content))
    expected["version"] = TEACHER_VIEW_VERSION
    assert actual_payload(drafts[1]).model_dump(mode="json") == expected


def test_protection_is_independent_of_forward_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lab_generate_skill.teacher.context_projection as forward

    c = teacher_projection_case("reddit")
    project, protect = build_teacher_context(c.policy)
    draft = project.project(c.source, c.raw, c.policy)[1]

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Forward projector must not verify itself")

    monkeypatch.setattr(forward, "project_fields", forbidden)
    assert all(
        x.status == "pass" for x in protect.verify(c.source, c.raw, draft, c.policy)
    )
    with pytest.raises(AssertionError):
        project.project(c.source, c.raw, c.policy)


@pytest.mark.parametrize(
    "mutation",
    [
        "early_event",
        "candidate",
        "round",
        "status",
        "skill",
        "feedback",
        "action_missing",
        "action_null",
        "action_error",
        "adjacency",
        "source_index_type",
        "terminal_provenance",
        "actor_visible",
        "extra_field",
        "page_value",
        "page_id",
        "page_lines",
        "page_reference",
        "unused_page",
        "protocol",
        "varying_numeric",
        "system",
        "format",
        "audit",
    ],
)
def test_actual_rendered_corruption_cannot_pass_by_rebinding_input_digest(
    mutation: str,
) -> None:
    c = teacher_projection_case("shopping_admin")
    project, protect = build_teacher_context(c.policy)
    draft = project.project(c.source, c.raw, c.policy)[1]
    payload: Any = actual_payload(draft).model_dump(mode="json")
    attempt = payload["evidence"]["attempts"][0]
    events = attempt["events"]
    if mutation == "early_event":
        events.pop(0)
    elif mutation == "candidate":
        attempt["candidate_id"] = "candidate-1"
    elif mutation == "round":
        attempt["revision_round"] = 2
    elif mutation == "status":
        attempt["status"] = "success"
    elif mutation == "skill":
        attempt["skill"]["instructions"] = "changed instructions"
    elif mutation == "feedback":
        attempt["feedback"]["status"] = "success"
    elif mutation == "action_missing":
        events[1]["recorded_action"] = {"state": "nonempty", "value": "click('999')"}
    elif mutation == "action_null":
        events[3]["recorded_action"] = {"state": "missing"}
    elif mutation == "action_error":
        events[1]["message_extra"]["operation_result"]["error"] = ""
    elif mutation == "adjacency":
        events[1]["observation_before"] = 2
    elif mutation == "source_index_type":
        events[0]["source_message_index"] = False
    elif mutation == "terminal_provenance":
        events[-2]["observation"].pop("observation_record_source")
    elif mutation == "actor_visible":
        events[0]["observation"]["actor_visible_input"]["text"] = "later terminal"
    elif mutation == "extra_field":
        events[0]["observation"].pop("unknown_tree")
    elif mutation == "page_value":
        payload["pages"][0]["text"] = payload["pages"][0]["text"].replace(
            "SKU", "OTHER"
        )
    elif mutation == "page_id":
        payload["pages"][0]["page_id"] = "p42"
    elif mutation == "page_lines":
        payload["pages"][0]["text"] = payload["pages"][0]["text"].splitlines()[0]
    elif mutation == "page_reference":
        events[0]["observation"]["axtree_txt"] = {"page_ref": "p1"}
    elif mutation == "unused_page":
        payload["pages"].append({"page_id": "p2", "text": "new unapproved material"})
    elif mutation == "protocol":
        payload["observation_protocol"]["observation_policy"] = {"version": True}
    elif mutation == "varying_numeric":
        events[0]["observation"]["numeric"][0] = True
    elif mutation == "format":
        payload["version"] = "teacher-required-evidence-projection-v1"
    actual = TeacherModelInput.model_validate_json(draft.input_bytes)
    messages = actual.messages
    system = (
        messages[0].model_copy(update={"content": messages[0].content + " changed"})
        if mutation == "system"
        else messages[0]
    )
    actual = TeacherModelInput(
        messages=(
            system,
            messages[1].model_copy(
                update={
                    "content": json.dumps(
                        payload, ensure_ascii=False, separators=(",", ":")
                    )
                }
            ),
        )
    )
    raw = actual.model_dump_json().encode()
    audit = draft.audit.model_copy(
        update={
            "input_sha256": context_bytes_sha(raw),
            "changes": (
                draft.audit.changes[1:] if mutation == "audit" else draft.audit.changes
            ),
        }
    )
    changed = ContextInputDraft.model_validate(
        {**draft.model_dump(), "input_bytes": raw, "audit": audit}
    )
    assert all(
        x.status == "fail" for x in protect.verify(c.source, c.raw, changed, c.policy)
    )
    if mutation != "audit":
        with pytest.raises((EvidenceIntegrityError, ValueError)):
            teacher_audit(c.source, c.allowed, c.policy, changed.kind, actual)


def rebound(
    c: TeacherProjectionCase, evidence: dict[str, JsonValue]
) -> TeacherProjectionCase:
    message = c.allowed.messages[1].model_copy(update={"content": json_text(evidence)})
    allowed = AllowedTeacherEvidence.model_validate(
        c.allowed.model_copy(update={"messages": (c.allowed.messages[0], message)})
    )
    raw = allowed.model_dump_json().encode()
    ref = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-input/1",
            visibility="teacher",
            producer="unit-approved-teacher-only",
        ),
    )
    return replace(
        c,
        allowed=allowed,
        raw=raw,
        source=c.source.model_copy(update={"allowed_input_ref": ref}),
    )


def test_empty_page_empty_trajectory_opaque_and_null_observations_and_varying_protocol_are_preserved() -> (
    None
):
    c = teacher_projection_case()
    evidence: Any = native_evidence(c.allowed.messages[1].content)
    evidence["initial_observation"] = ""
    evidence["attempts"][1]["trajectory"] = []
    messages = evidence["attempts"][0]["trajectory"]
    messages[0]["content"] = ""
    messages[2]["content"] = None
    body = json.loads(messages[4]["content"])
    body["observation_policy"] = {"version": True}
    body["goal"] = "Different complete observed goal"
    messages[4]["content"] = json_text(body)
    c = rebound(c, evidence)
    project, protect = build_teacher_context(c.policy)
    draft = project.project(c.source, c.raw, c.policy)[1]
    view: Any = actual_payload(draft).model_dump(mode="json")
    assert "observation_policy" not in view["observation_protocol"]
    assert (
        view["pages"][0]["text"] == ""
        and view["evidence"]["attempts"][1]["events"] == []
    )
    events = view["evidence"]["attempts"][0]["events"]
    assert events[0]["observation"] == "" and events[2]["observation"] is None
    assert events[4]["observation"]["goal"] == "Different complete observed goal"
    assert all(
        x.status == "pass" for x in protect.verify(c.source, c.raw, draft, c.policy)
    )


@pytest.mark.parametrize(
    "change",
    [
        "format",
        "schema",
        "extra",
        "empty_messages",
        "wrong_roles",
        "empty_task",
        "round_bool",
        "round_range",
        "scope",
        "duplicate_outer",
        "duplicate_inner",
        "nan",
        "infinity",
        "reserved",
        "missing_trajectory",
        "wrong_page",
        "missing_content",
        "empty_attempts",
    ],
)
def test_source_format_illegal_empty_types_and_unsupported_cases_refuse_explicitly(
    change: str,
) -> None:
    c = teacher_projection_case()
    doc: Any = json.loads(c.raw)
    evidence: Any = json.loads(doc["messages"][1]["content"])
    if change == "format":
        doc["format_version"] = "guessed"
    elif change == "schema":
        doc["schema_version"] = "teacher-input/2"
    elif change == "extra":
        doc["ignored"] = None
    elif change == "empty_messages":
        doc["messages"] = []
    elif change == "wrong_roles":
        doc["messages"][0]["role"] = "assistant"
    elif change == "empty_task":
        evidence["task"] = ""
    elif change == "round_bool":
        doc["teacher_round"] = True
    elif change == "round_range":
        doc["teacher_round"] = 4
    elif change == "scope":
        doc["scope"]["task"]["source_task_id"] = "foreign"
    elif change == "duplicate_outer":
        raw = c.raw[:-1] + b',"teacher_round":3}'
        source = c.source.model_copy(
            update={
                "allowed_input_ref": evidence_reference(
                    raw,
                    EvidenceMetadata(
                        media_type="application/json",
                        content_schema="teacher-input/1",
                        visibility="teacher",
                        producer="unit",
                    ),
                )
            }
        )
        with pytest.raises(EvidenceIntegrityError):
            build_teacher_context(c.policy)[0].project(source, raw, c.policy)
        return
    elif change == "duplicate_inner":
        doc["messages"][1][
            "content"
        ] = '{"task":"x","task":"y","initial_observation":"","attempts":[]}'
    elif change in ("nan", "infinity"):
        doc["messages"][1]["content"] = (
            '{"task":"x","initial_observation":"","attempts":[],"bad":'
            + ("NaN" if change == "nan" else "1e999")
            + "}"
        )
    elif change == "reserved":
        evidence["attempts"][0]["events"] = []
    elif change == "missing_trajectory":
        evidence["attempts"][0].pop("trajectory")
    elif change == "wrong_page":
        body = json.loads(evidence["attempts"][0]["trajectory"][0]["content"])
        body["axtree_txt"] = {"page_ref": "already_encoded"}
        evidence["attempts"][0]["trajectory"][0]["content"] = json_text(body)
    elif change == "missing_content":
        evidence["attempts"][0]["trajectory"][0].pop("content")
    else:
        evidence["attempts"] = []
    if change not in ("duplicate_inner", "nan", "infinity", "empty_messages"):
        doc["messages"][1]["content"] = json_text(evidence)
    with pytest.raises((ValidationError, ValueError)):
        AllowedTeacherEvidence.model_validate_json(json.dumps(doc))


def test_role_round_policy_scope_and_original_bytes_do_not_cross_roles() -> None:
    c = teacher_projection_case()
    project, protect = build_teacher_context(c.policy)
    actor = actor_projection_case()
    with pytest.raises(TypeError):
        project.project(actor.source, c.raw, c.policy)
    with pytest.raises(ValueError):
        build_teacher_context(actor.policy)
    with pytest.raises(ValueError):
        build_teacher_context(
            c.policy.model_copy(
                update={"candidate_order": ("identity", "structured_fields")}
            )
        )
    with pytest.raises(OwnershipConflict):
        project.project(
            c.source.model_copy(update={"teacher_round": 1}), c.raw, c.policy
        )
    with pytest.raises(EvidenceIntegrityError):
        project.project(c.source, c.raw + b" ", c.policy)
    changed = ContextProjectionPolicy.model_validate(
        c.policy.model_copy(update={"implementation_sha256": "f" * 64})
    )
    with pytest.raises(OwnershipConflict):
        project.project(c.source, c.raw, changed)
    assert read_json('{"a":true,"b":1,"c":1.0}') == {"a": True, "b": 1, "c": 1.0}
    with pytest.raises(ValueError):
        read_json("[" * 66 + "0" + "]" * 66)
