"""Decision guidance follows actual projection and registered tools independently."""

import hashlib
import json
from typing import Any

import pytest

from lab_generate_skill.actor.adaptive_layout import adaptive_frame
from lab_generate_skill.actor.adaptive_projection import AdaptiveActorProjector
from lab_generate_skill.actor.adaptive_protection import AdaptiveActorProtection
from lab_generate_skill.actor.observation_read_response import parse_observation_read
from lab_generate_skill.actor.protocol_examples import read_examples
from lab_generate_skill.domain.actor_prompt import ActorHistoryItem, ActorPrompt
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorProposalFeedback,
    ActorProposalError,
)
from lab_generate_skill.domain.actor_response import ActorTextCompletion
from lab_generate_skill.policies.actor_proposal_identity import (
    counted_proposal_feedback,
)
from lab_generate_skill.actor.history_layout import history_sections
from lab_generate_skill.domain.observation_read import (
    ReadObservationRegions,
    ObservationRegionRange,
)
from lab_generate_skill.policies.observation_pages import observation_page
from lab_generate_skill.policies.observation_search import index_literal_search
from lab_generate_skill.policies.observation_viewport import public_viewport_ranges

from actor_view_guidance_fixtures import guidance_case
from test_adaptive_context_repair import pure_case
from retrieval_fixtures import reference


def drafts(case: tuple[Any, ...]) -> tuple[Any, ...]:
    public, index, source, policy = case
    return AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )


@pytest.mark.parametrize(
    "measured,unknown,expected",
    [
        (None, False, "structural"),
        ("before-scroll", False, "viewport"),
        ("before-scroll", True, "structural"),
    ],
)
def test_one_current_view_per_candidate_uses_actual_geometry_selection(
    measured: str | None, unknown: bool, expected: str
) -> None:
    case = guidance_case(measured=measured, geometry_unknown=unknown)
    public, index, source, policy = case
    candidates = drafts(case)
    assert len(candidates) == 3
    for draft in candidates:
        prompt = ActorPrompt.model_validate_json(draft.input_bytes)
        system, user = (message.content for message in prompt.messages)
        assert user.count("# Current view\n") == 1
        assert system.count("# Enabled tools") == 1
        assert "scroll(delta_x:" in system and "read_region(ranges:" in system
        assert "without viewport" not in system
        assert "# Allowed business actions" not in user
        assert user.count("# Complete format examples") == 1
        assert "# Current proposal state" not in user and "# Reading notice" not in user
        for name in (
            "reads_remaining",
            "reads_used",
            "consecutive_invalid",
            "repeated_invalid",
            "no_progress",
            "current_tab_count",
        ):
            assert name not in user
        if draft.kind == "compact_full_ax":
            assert "Complete captured content is displayed" in user
            assert (
                "Structural local view" not in user
                and "Viewport-priority local view" not in user
            )
            assert "Captured but unshown: none." in user
        else:
            is_viewport = (
                draft.candidate_id == "local_ax_navigation" and expected == "viewport"
            )
            assert ("Viewport-priority local view" in user) == is_viewport
            assert ("Structural local view" in user) == (not is_viewport)
            assert "Complete captured content is displayed" not in user
            body = prompt.observation_view.body(user) if prompt.observation_view else ""
            metadata = json.loads(body.splitlines()[2])
            assert metadata["uncaptured_or_pending"] == "unknown"
            assert metadata["displayed"].startswith("Original source fragments")
        checks = AdaptiveActorProtection(policy, lambda _: index).verify(
            source, public.model_dump_json().encode(), draft, policy
        )
        assert checks and all(check.status == "pass" for check in checks)
    assert bool(public_viewport_ranges(index)) == (expected == "viewport")


@pytest.mark.parametrize(
    "reads_used,notice",
    [
        (2, None),
        (3, "3 reads remain"),
        (4, "2 reads remain"),
        (5, "1 read remains"),
        (6, "No reads remain"),
    ],
)
def test_reading_notice_is_only_shown_near_quota_or_at_exhaustion(
    reads_used: int, notice: str | None
) -> None:
    case = guidance_case(reads_used=reads_used)
    prompt = ActorPrompt.model_validate_json(drafts(case)[0].input_bytes)
    user = prompt.messages[1].content
    assert "# Current proposal state" not in user
    assert ("# Reading notice" in user) == (notice is not None)
    if notice:
        assert notice in user
    assert prompt.observation_view and prompt.observation_view.reads_used == reads_used


@pytest.mark.parametrize("consecutive,identical,near", [(6, 4, False), (3, 2, True)])
def test_rejection_shows_its_correction_without_model_counter_dump(
    consecutive: int, identical: int, near: bool
) -> None:
    case = guidance_case(
        changes={
            "max_consecutive_invalid_proposals": consecutive,
            "max_identical_invalid_proposals": identical,
        }
    )
    public = case[0]
    prompt = ActorPrompt.model_validate_json(drafts(case)[0].input_bytes)
    completion = ActorTextCompletion(
        generation_id="guidance-feedback",
        request_id="guidance-feedback",
        input_ref=reference(prompt, "actor-model-input/1"),
        model_input_sha256=hashlib.sha256(prompt.input_bytes()).hexdigest(),
        parameters_ref=reference({"software_fixture": True}, "model-parameters/1"),
        text=json.dumps({"read": {"tool": "read_region", "ranges": []}}),
        finish_reason="stop",
    )
    feedback = counted_proposal_feedback(
        ActorProposalError(
            ActorProposalFeedback(
                code="INVALID_ARGUMENTS",
                tool="read_region",
                message="ranges must be nonempty",
                field="ranges",
                actual=0,
                allowed="at least one range",
                next_action="Use a region_id from the current public directory.",
            )
        ),
        prompt,
        completion,
    )
    assert feedback.consecutive_invalid == feedback.repeated_invalid == 1
    assert feedback.can_correct and not feedback.executed
    assert ("will stop this run" in feedback.next_action) == near
    public = public.model_copy(
        update={
            "history": (
                ActorHistoryItem(
                    schema_version="actor-history-item/2",
                    executed=False,
                    action=completion.text,
                    error=feedback.model_dump_json(),
                ),
            )
        }
    )
    rendered = history_sections(public, concise_rejections=True)
    assert "ranges must be nonempty" in rendered and "Use a region_id" in rendered
    assert '"executed": false' in rendered
    assert "consecutive_invalid" not in rendered and "repeated_invalid" not in rendered
    assert "Corrections remaining" not in rendered
    assert feedback.model_dump()["consecutive_invalid"] == 1


@pytest.mark.parametrize(
    "tools",
    [
        (),
        ("list_regions",),
        ("read_region",),
        ("search_regions",),
        ("list_regions", "read_region", "search_regions"),
    ],
)
def test_only_registered_read_rules_and_tools_are_published_without_hiding_scroll(
    tools: tuple[str, ...],
) -> None:
    case = guidance_case(tools=tools)
    public, _, _, _ = case
    for draft in drafts(case):
        prompt = ActorPrompt.model_validate_json(draft.input_bytes)
        system = prompt.messages[0].content
        assert "scroll(delta_x:" in system
        for name in ("list_regions", "read_region", "search_regions"):
            assert (name + "(" in system) == (name in tools)
        assert ("Search covers only" in system) == ("search_regions" in tools)
        assert ("Reads do not expand" in system) == bool(tools)
        assert ("Reads use current public region_ids" in system) == bool(tools)
        assert ("known region_ids can be read directly" in system) == (
            "read_region" in tools
        )
        for number, example in enumerate(read_examples(public)):
            request = parse_observation_read(
                json.dumps(example), "stop", prompt, request_id=f"guidance-{number}"
            )
            assert request is not None and request.tool in tools
    if not tools:
        assert len(drafts(case)) == 1


@pytest.mark.parametrize("limit", [1, 4, 8])
def test_effective_range_limit_in_fixed_contract_matches_program_schema(
    limit: int,
) -> None:
    case = guidance_case(changes={"max_ranges": limit})
    public = case[0]
    system = adaptive_frame(public)[0]
    assert f"ranges:array<" in system and f"[1..{limit}]" in system
    assert "[1..16]" not in system
    assert "current_snapshot_sha256" in system and "current_tab_count-1" in system
    assert public.observation_source is not None
    assert public.observation_source.snapshot.observation_ref.sha256 not in system


def test_scroll_replaces_view_and_snapshot_without_duplicating_fixed_system_or_history() -> (
    None
):
    before = guidance_case(measured="before-scroll")
    after = guidance_case(measured="after-scroll")
    first = ActorPrompt.model_validate_json(
        next(
            d for d in drafts(before) if d.candidate_id == "local_ax_navigation"
        ).input_bytes
    )
    second = ActorPrompt.model_validate_json(
        next(
            d for d in drafts(after) if d.candidate_id == "local_ax_navigation"
        ).input_bytes
    )
    assert first.messages[0].content == second.messages[0].content
    assert len(first.messages) == len(second.messages) == 2
    assert first.observation_view and second.observation_view
    assert (
        first.observation_view.snapshot.observation_ref
        != second.observation_view.snapshot.observation_ref
    )
    first_body = first.observation_view.body(first.messages[1].content)
    second_body = second.observation_view.body(second.messages[1].content)
    assert (
        "Top public target" in first_body and "Bottom public target" not in first_body
    )
    assert (
        "Bottom public target" in second_body and "Top public target" not in second_body
    )
    for prompt in (first, second):
        assert prompt.messages[1].content.count("# Current view\n") == 1
        assert prompt.messages[1].content.count("Viewport-priority local view") == 1


def test_omitted_captured_content_is_explicit_and_readable_without_guessing_region_ids() -> (
    None
):
    case = guidance_case(measured="before-scroll")
    _, index, _, _ = case
    prompt = ActorPrompt.model_validate_json(
        next(
            d for d in drafts(case) if d.candidate_id == "local_ax_navigation"
        ).input_bytes
    )
    assert prompt.observation_view
    body = prompt.observation_view.body(prompt.messages[1].content)
    metadata = json.loads(body.splitlines()[2])
    missing = metadata["captured_but_unshown"]
    assert missing["range_count"] > 0 and "read_region" in missing["available_tools"]
    assert "Navigation entry" in body and "Bottom public target" not in body
    node = next(
        node for node in index.nodes if "Bottom public target" in index.lines[node.line]
    )
    region = index.regions[node.line]
    assert any(
        start <= region.opening_span.start and region.opening_span.end <= end
        for start, end in missing["ranges"]
    )
    request = ReadObservationRegions(
        request_id="retained-offscreen",
        snapshot=index.snapshot,
        output_tokens=1000,
        ranges=(
            ObservationRegionRange(region_id=region.region_id, unit="whole_region"),
        ),
    )
    result = observation_page(
        index,
        request,
        offset=0,
        limit=index.policy.page_units,
        next_cursor="fixture-next",
        search=index_literal_search(index),
    ).payload
    assert "Bottom public target" in "".join(
        fragment.text for fragment in result.fragments
    )


def test_false_viewport_statement_fails_independent_protection_even_with_rehashed_body() -> (
    None
):
    case = guidance_case()
    public, index, source, policy = case
    draft = drafts(case)[1]
    prompt = ActorPrompt.model_validate_json(draft.input_bytes)
    assert prompt.observation_view
    user = prompt.messages[1].content.replace(
        "Structural local view", "Viewport-priority local view"
    )
    old_body = prompt.observation_view.body(prompt.messages[1].content)
    body = old_body.replace("Structural local view", "Viewport-priority local view")
    changed = prompt.model_copy(
        update={
            "messages": (
                prompt.messages[0],
                prompt.messages[1].model_copy(update={"content": user}),
            ),
            "observation_view": prompt.observation_view.model_copy(
                update={
                    "body_end": prompt.observation_view.body_start + len(body),
                    "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                }
            ),
        }
    )
    changed = ActorPrompt.model_validate_json(changed.model_dump_json())
    checks = AdaptiveActorProtection(policy, lambda _: index).verify(
        source,
        public.model_dump_json().encode(),
        draft.model_copy(update={"input_bytes": changed.model_dump_json().encode()}),
        policy,
    )
    assert checks and all(check.status == "fail" for check in checks)


def test_current_mode_note_is_not_added_to_history_and_old_prompt_contract_stays_v1() -> (
    None
):
    public, index, source, policy = pure_case(
        history=(
            ActorHistoryItem(
                schema_version="actor-history-item/2",
                executed=True,
                action="scroll(0,100)",
                error="",
            ),
        )
    )
    candidates = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )
    for draft in candidates:
        prompt = ActorPrompt.model_validate_json(draft.input_bytes)
        assert prompt.prompt_version.endswith("-v1")
        assert "# Current view\n" not in prompt.messages[1].content
        assert "scroll(0,100)" in prompt.messages[1].content
        assert (
            b'"tab_count"' not in draft.input_bytes
            and b'"invalid_proposals"' not in draft.input_bytes
        )


@pytest.mark.parametrize(
    "threshold,remaining,visible",
    [
        (3, 4, False),
        (3, 3, True),
        (3, 2, True),
        (5, 6, False),
        (5, 5, True),
        (5, 4, True),
    ],
)
def test_reading_warning_starts_at_the_selected_frozen_threshold(
    threshold: int, remaining: int, visible: bool
) -> None:
    case = guidance_case(
        changes={"reads_per_observation": 10, "warn_remaining": threshold},
        reads_used=10 - remaining,
    )
    prompt = ActorPrompt.model_validate_json(drafts(case)[0].input_bytes)
    assert ("# Reading notice" in prompt.messages[1].content) == visible
    if visible:
        assert f"{remaining} reads remain" in prompt.messages[1].content
    assert (
        prompt.observation_view
        and prompt.observation_view.policy.warn_remaining == threshold
    )


def test_warning_threshold_does_not_change_the_normal_complete_model_messages() -> None:
    baseline = None
    for threshold in (2, 3, 5):
        case = guidance_case(
            measured="before-scroll",
            changes={"reads_per_observation": 10, "warn_remaining": threshold},
        )
        current = tuple(
            ActorPrompt.model_validate_json(draft.input_bytes).input_bytes()
            for draft in drafts(case)
        )
        if baseline is not None:
            assert current == baseline
        baseline = current
