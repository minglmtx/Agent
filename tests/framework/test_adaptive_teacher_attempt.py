"""Real Actor read facts through actual Teacher source/review, synthetic rights."""

import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import JsonValue
from lab_generate_skill.application.teacher_attempt import publish_teacher_attempt
from lab_generate_skill.application.teacher_attempt_review import review_teacher_attempt
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.teacher_input import (
    AllowedTeacherEvidence,
    TeacherChatMessage,
    TeacherModelInput,
)
from lab_generate_skill.domain.context_projection import TeacherContextSource
from lab_generate_skill.bootstrap.context_projection import build_teacher_context
from lab_generate_skill.domain.teacher_attempt import (
    TeacherAttemptReceipt,
    PublishedTeacherAttempt,
)
from lab_generate_skill.domain.teacher_source import TeacherAttemptView
from lab_generate_skill.domain.teacher_json import json_value
from lab_generate_skill.teacher.instructions import teacher_projection_guide
from adaptive_teacher_fixtures import adaptive_teacher_case
from teacher_attempt_fixtures import put
from test_run_journal import command
from teacher_context_fixtures import teacher_projection_case


@pytest.mark.parametrize("mode", ["read", "duplicate"])
def test_original_read_return_and_actual_input_delivery_remain_distinct_in_teacher(
    tmp_path: Path,
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = adaptive_teacher_case(tmp_path, mode=mode)
    actor = c.actor
    store = actor.base.base.loop.store
    controls = actor.base.base.loop.journal.controls
    before = len(actor.base.base.channel.sent)
    published = publish_teacher_attempt(
        c.original, c.deps, control=controls.bind(c.original.operation)
    )
    allowed = TeacherAttemptView.model_validate_json(
        store.read(published.source.allowed_view_ref)
    )
    native: Any = allowed.native
    assert native["recording_format"] == "teacher-original-actor-attempt/2"
    assert native["generation_rounds"] == 2 and native["steps"] == (
        1 if mode == "read" else 0
    )
    messages = native["trajectory"]
    event = messages[1]["observation_read"]
    assert event["status"] == "returned" and event["return_available"] is True
    assert event["delivery_records"][0]["generation_index"] == 1
    assert event["delivery_records"][0]["delivery"] == "included_in_model_input"
    first = json.loads(messages[0]["content"])
    second = json.loads(messages[2]["content"])
    assert first["axtree_txt"] == second["axtree_txt"]
    assert (
        second["actor_observation_view"]["active_read_result_sha256"]
        == event["returned_result_sha256"]
    )
    assert second["actor_observation_view"]["delivery"] == "included_in_model_input"
    if mode == "read":
        assert "Value-3" in event["returned_body"] and native["success"] is True
        assert messages[1]["operation_result"]["status"] == "no_recorded_action"
    else:
        final = messages[3]["observation_read"]
        assert final["status"] == "returned" and final["delivery_records"] == []
        assert native["success"] is None and native["stop_reason"] == "error"
    rendered = json.dumps(native)
    assert all(
        value not in rendered
        for value in (
            '"owner_id"',
            '"run_id"',
            '"policy_sha256"',
            "cas://",
            "NOT_FOR_MODEL",
            "UNIT_PRIVATE_DIAGNOSTIC",
        )
    )
    guide = teacher_projection_guide({"attempts": [allowed.native]})
    assert "does not prove" in guide and "observation_read" in guide
    evidence: dict[str, JsonValue] = {
        "task": actor.request.task.goal,
        "public_task": json_value(actor.request.task.model_dump(mode="json")),
        "initial_observation": first["axtree_txt"],
        "retrieved_skills": json_value([actor.request.skill.model_payload()] * 6),
        "attempts": [allowed.native],
        "revision_request": {"round": 1},
    }
    permitted = AllowedTeacherEvidence(
        scope=c.original.scope,
        task=actor.request.task,
        teacher_round=1,
        messages=(
            TeacherChatMessage(
                role="system", content=teacher_projection_guide(evidence)
            ),
            TeacherChatMessage(role="user", content=json.dumps(evidence)),
        ),
    )
    raw = permitted.model_dump_json().encode()
    ref = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-input/1",
            visibility="teacher",
            producer="unit-adaptive-permitted-evidence",
        ),
    )
    source = TeacherContextSource(
        scope=c.original.scope, teacher_round=1, allowed_input_ref=ref
    )
    policy = teacher_projection_case().policy
    project, protect = build_teacher_context(policy)
    drafts = project.project(source, raw, policy)
    assert len(drafts) == 2
    for draft in drafts:
        assert all(
            check.status == "pass"
            for check in protect.verify(source, raw, draft, policy)
        )
        actual = TeacherModelInput.model_validate_json(draft.input_bytes)
        assert "observation_read" in actual.messages[1].content
    import lab_generate_skill.teacher.observation_read as forward

    def forbidden(*args: object, **kw: object) -> None:
        raise AssertionError("Independent Teacher review called forward read composer")

    monkeypatch.setattr(forward, "observation_read_event", forbidden)
    monkeypatch.setattr(forward, "observation_input_view", forbidden)
    op = command(
        "review-original-read-teacher", cleanup_parent=c.original.operation.operation_id
    )
    assert (
        review_teacher_attempt(
            published, c.review, op, control=controls.bind(op)
        ).source
        == published.source
    )
    assert (
        len(actor.base.base.channel.sent) == before
        and actor.session.calls == 2
        and actor.session.closed == 1
    )


@pytest.mark.parametrize(
    "fault", ["returned_body", "delivery", "view_ranges", "private_extra"]
)
def test_rebound_teacher_read_view_cannot_change_source_or_invent_delivery(
    tmp_path: Path, fault: str
) -> None:
    c = adaptive_teacher_case(tmp_path)
    store = c.actor.base.base.loop.store
    controls = c.actor.base.base.loop.journal.controls
    published = publish_teacher_attempt(
        c.original, c.deps, control=controls.bind(c.original.operation)
    )
    allowed = TeacherAttemptView.model_validate_json(
        store.read(published.source.allowed_view_ref)
    )
    native: Any = json.loads(json.dumps(allowed.native))
    if fault == "returned_body":
        native["trajectory"][1]["observation_read"][
            "returned_body"
        ] = "forged public row"
    elif fault == "delivery":
        native["trajectory"][1]["observation_read"]["delivery_records"][0][
            "generation_index"
        ] = 0
    elif fault == "view_ranges":
        body = json.loads(native["trajectory"][2]["content"])
        body["actor_observation_view"]["source_ranges"] = []
        native["trajectory"][2]["content"] = json.dumps(body)
    else:
        native["trajectory"][1]["observation_read"]["private_scope"] = {
            "owner_id": "forged"
        }
    changed = allowed.model_copy(update={"native": native})
    ref = store.put(
        changed.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-attempt-input/1",
            visibility="teacher",
            producer="unit-forged-rebound",
        ),
    )
    source = published.source.model_copy(update={"allowed_view_ref": ref})
    receipt = TeacherAttemptReceipt.model_validate_json(
        store.read(published.receipt_ref)
    ).model_copy(update={"source": source})
    altered = PublishedTeacherAttempt(receipt_ref=put(store, receipt), source=source)
    op = command(
        "review-altered-read-teacher", cleanup_parent=c.original.operation.operation_id
    )
    with pytest.raises(EvidenceIntegrityError):
        review_teacher_attempt(altered, c.review, op, control=controls.bind(op))
