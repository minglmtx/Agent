"""Local conservative ID/guide changes; no model, browser or quality claims."""

from dataclasses import replace
import re
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.actor.rails_diagnostic_ax import diagnostic_ax_view
from lab_generate_skill.actor.context_ax_protection import diagnostic_changes
from lab_generate_skill.actor.map_rails_projection import ADDRESSABLE_SCOPE
from lab_generate_skill.bootstrap.actor_projection import build_actor_projection
from lab_generate_skill.bootstrap.context_projection import (
    build_actor_context,
    build_teacher_context,
)
from lab_generate_skill.domain.actor_projection import (
    MapRailsAddressableProjection,
    MapRailsDiagnosticProjection,
    actor_projection_configuration,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.teacher_input import TeacherModelInput
from lab_generate_skill.domain.teacher_projection import TeacherProjectionPayload
from lab_generate_skill.domain.teacher_json import object_value, array_value
from lab_generate_skill.teacher.instructions import GUIDE
from actor_context_projection_fixtures import actor_projection_case, ActorProjectionCase
from map_actor_view_fixtures import original_turn
from teacher_context_fixtures import teacher_projection_case


def addressable_case() -> ActorProjectionCase:
    turn, _ = original_turn()
    c = actor_projection_case(original=turn, structural=True)
    return replace(
        c,
        policy=ContextProjectionPolicy.model_validate(
            {
                **c.policy.model_dump(),
                "actor_projection": MapRailsAddressableProjection(),
            }
        ),
    )


def test_new_map_version_preserves_every_original_id_and_rejects_old_removal() -> None:
    c = addressable_case()
    project, protect = build_actor_context(c.policy)
    identity, actual = project.project(c.source, c.raw, c.policy)
    prompt = ActorPrompt.model_validate_json(actual.input_bytes)
    assert prompt.prompt_version == "browsergym-map-rails-diagnostic-ax-v2"
    original = c.turn.observation.text
    assert original is not None
    original_ids = re.findall(r"^\s*\[(\d+)\]", original, re.M)
    new_ids = re.findall(r"^ *\[(\d+)\]", prompt.messages[1].content, re.M)
    assert original_ids and original_ids == new_ids
    assert {v.operation for v in actual.audit.changes} == {"layout", "omit_duplicate"}
    assert ADDRESSABLE_SCOPE in prompt.messages[1].content
    assert all(
        v.status == "pass" for v in protect.verify(c.source, c.raw, actual, c.policy)
    )
    assert project.project(c.source, c.raw, c.policy) == (identity, actual)
    # A freshly rebound audit cannot admit legacy ID removal under the new policy.
    old = build_actor_projection(MapRailsDiagnosticProjection())(c.turn)
    from lab_generate_skill.actor.context_protection import actor_audit

    with pytest.raises(EvidenceIntegrityError):
        actor_audit(c.source, c.turn, c.policy, "structural_ax", old)


@pytest.mark.parametrize("role", ["row", "rowgroup", "paragraph"])
@pytest.mark.parametrize("ending", ["\n", "\r\n", ""])
def test_v2_retains_empty_structure_ids_depth_and_addressable_static_text(
    role: str, ending: str
) -> None:
    original = f"RootWebArea 'x'\n\t[1] {role} ''\n\t\t[2] gridcell 'x'\n\t\t\tStaticText 'x'\n\t\t\t[3] StaticText 'x'{ending}"
    view = diagnostic_ax_view(original, preserve_ids=True)
    assert view.structural_ids == 0 and view.duplicate_leaves == 1
    assert f"  [1] {role} ''\n" in view.text
    assert "      [3] StaticText 'x'" + ending in view.text
    changes = diagnostic_changes(original, view.text, view.text, preserve_ids=True)
    assert all(v.operation != "remove_empty_id" for v in changes)
    changed = view.text.replace(f"[1] {role}", role)
    with pytest.raises(EvidenceIntegrityError):
        diagnostic_changes(original, changed, changed, preserve_ids=True)


@pytest.mark.parametrize(
    "invalid", [None, "", 0, True, {}, [], " \n", "\t[1] row ''\n\t[1] row ''"]
)
def test_new_ax_invalid_and_duplicate_input_refuses_without_guessing(
    invalid: object,
) -> None:
    with pytest.raises((ValueError, TypeError)):
        diagnostic_ax_view(cast(str, invalid), preserve_ids=True)


@pytest.mark.parametrize("bad", [None, 0, 1, "true", []])
def test_id_mode_requires_exact_boolean(bad: object) -> None:
    with pytest.raises(TypeError):
        diagnostic_ax_view("Root", preserve_ids=cast(bool, bad))
    with pytest.raises(TypeError):
        diagnostic_changes("Root", "Root", "Root", preserve_ids=cast(bool, bad))


def test_new_version_is_explicit_legacy_configuration_and_first_12_bytes_stay_exact() -> (
    None
):
    assert (
        actor_projection_configuration(MapRailsAddressableProjection().model_dump())
        == MapRailsAddressableProjection()
    )
    for i in range(12):
        turn, original = original_turn(i)
        assert build_actor_projection(MapRailsAddressableProjection())(turn) == original
    c = addressable_case()
    foreign_identity = c.turn.task.identity.model_copy(
        update={"source_task_id": "other"}
    )
    foreign_task = c.turn.task.model_copy(update={"identity": foreign_identity})
    foreign_record = c.turn.observation.record.model_copy(
        update={"task": foreign_identity}
    )
    foreign = c.turn.model_copy(
        update={
            "task": foreign_task,
            "observation": c.turn.observation.model_copy(
                update={"record": foreign_record}
            ),
        }
    )
    with pytest.raises(OwnershipConflict):
        build_actor_projection(MapRailsAddressableProjection())(foreign)
    for key, bad in [
        ("contract_version", True),
        ("extra", 1),
        ("schema_version", "actor-map-rails-diagnostic-projection/3"),
    ]:
        with pytest.raises(ValidationError):
            actor_projection_configuration(
                {**MapRailsAddressableProjection().model_dump(), key: bad}
            )


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_teacher_guide_matches_actual_shared_protocol_wrappers_and_local_result_links(
    site: Site,
) -> None:
    c = teacher_projection_case(site)
    project, protect = build_teacher_context(c.policy)
    draft = project.project(c.source, c.raw, c.policy)[1]
    messages = TeacherModelInput.model_validate_json(draft.input_bytes)
    assert GUIDE.startswith("\n") and not GUIDE.startswith("\\n")
    assert "guide revision 4" in messages.messages[0].content
    payload = TeacherProjectionPayload.model_validate_json(messages.messages[1].content)
    assert set(payload.observation_protocol) == {
        "observation_scope",
        "observation_mode",
        "observation_policy",
    }
    attempts = array_value(payload.evidence["attempts"], "attempts")
    for i, item in enumerate(attempts):
        attempt = object_value(item, "attempt")
        assert (
            attempt["candidate_id"] == f"candidate-{i}"
            and attempt["candidate_index"] == i
        )
        events = array_value(attempt["events"], "events")
        first = object_value(events[0], "first")
        assert set(first) == {"source_message_index", "kind", "observation"}
        action = object_value(events[1], "action")
        assert action["observation_before"] == 0 and action["observation_after"] == 2
        assert (
            object_value(action["recorded_action"], "recorded action")["state"]
            == "missing"
        )
        outcome = object_value(
            object_value(action["message_extra"], "extra")["operation_result"],
            "outcome",
        )
        assert outcome["status"] == "unknown" and outcome["result"] is None
        terminal = object_value(
            object_value(events[-2], "terminal")["observation"], "observation"
        )
        assert (
            terminal["observation_record_source"] == "later_terminal_capture"
            and "actor_visible_input" not in terminal
        )
        assert (
            object_value(object_value(events[-1], "other")["message_extra"], "extra")[
                "turn"
            ]
            is True
        )
    reasons = {v.reason_code for v in draft.audit.changes}
    assert {
        "EXACT_GLOBAL_OBSERVATION_PROTOCOL",
        "EXACT_MESSAGE_POSITION",
        "NONASSISTANT_NULL_SERIALIZATION_WRAPPER",
    } <= reasons
    assert all(
        v.status == "pass" for v in protect.verify(c.source, c.raw, draft, c.policy)
    )
    assert project.project(c.source, c.raw, c.policy)[1] == draft


def test_historical_map_configuration_serialization_stays_exact_before_new_version() -> (
    None
):
    assert MapRailsDiagnosticProjection().model_dump_json().encode() == (
        b'{"schema_version":"actor-map-rails-diagnostic-projection/1","site":"map",'
        b'"family":"native_route_map_data","contract_version":1,"split":"train",'
        b'"source_task_id":"b9101b71aacd51b61f6e"}'
    )


def test_ID_preserving_original_measurement_is_rejected_by_unchanged_hard_gate() -> (
    None
):
    # Pure gate arithmetic with recorded measurements, not a new tokenizer proof.
    from context_budget_fixtures import profile, selection
    from lab_generate_skill.policies.context_budget import select_candidate

    p = profile(
        context_window=32768, output_reserve=4096, input_limit=28672, soft_target=24576
    )
    decision = select_candidate(
        selection(counts=(37839, 30825), configuration=p, structural=True)
    )
    assert not decision.accepted and decision.reason_code == "input_budget_exceeded"
    assert (
        decision.selected_input_ref is None and decision.selected_candidate_id is None
    )
    assert all(not a.within_hard for a in decision.assessments)
