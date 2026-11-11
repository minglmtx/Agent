"""Three concrete context defects through real projection/parser/count/loop ports."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from lab_generate_skill.actor.adaptive_layout import adaptive_frame
from lab_generate_skill.actor.adaptive_projection import AdaptiveActorProjector
from lab_generate_skill.actor.adaptive_protection import AdaptiveActorProtection
from lab_generate_skill.actor.context_source import ADAPTIVE_ACTOR_PROTECTION_RULES
from lab_generate_skill.actor.observation_read_response import parse_observation_read
from lab_generate_skill.actor.protocol_examples import action_example, read_examples
from lab_generate_skill.actor.response import parse_actor_action
from lab_generate_skill.domain.actor_prompt import (
    ActorHistoryItem,
    ActorPublicTurn,
    ActorPrompt,
)
from lab_generate_skill.domain.actor_observation_source import ActorObservationSource
from lab_generate_skill.domain.actor_projection import (
    AdaptiveObservationProjection,
    ObservationTaskBinding,
)
from lab_generate_skill.domain.context_projection import (
    ActorContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.actor_engine import LocalActorOutput
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.observation_read import (
    ListObservationRegions,
    SearchObservationRegions,
)
from lab_generate_skill.domain.trace_events import (
    GenerationPlanned,
    DecisionRejected,
    ReadPlanned,
    ReadObserved,
)
from lab_generate_skill.policies.observation_pages import observation_page
from lab_generate_skill.policies.observation_search import (
    index_literal_search,
    literal_search,
)
from lab_generate_skill.policies.observation_navigation import with_complete_navigation
from lab_generate_skill.policies.observation_protection import (
    verify_observation_read_window,
)
from adaptive_actor_loop_fixtures import adaptive_loop_case
from actor_context_projection_fixtures import actor_projection_case
from observation_fixtures import sample_observation
from observation_read_fixtures import indexed
from retrieval_fixtures import reference
from test_actor_protocol import turn

NAV = (
    "RootWebArea 'Captured page', focused\n"
    "\t[1] navigation 'Main navigation'\n"
    "\t\t[2] link 'First', focused\n"
    "\t\t[3] link 'Same label' disabled\n"
    "\t\t[4] menu 'Expanded menu' expanded=True\n"
    "\t\t\t[5] link 'Same label'\n"
    "\t\t\t[6] link 'Final navigation link'\n"
    "\t[7] table 'Loaded records'\n"
    "\t\t[8] row\n\t\t\t[9] columnheader 'Amount $'\n"
    "\t\t[10] row\n\t\t\t[11] gridcell '123.00'\n"
)

LARGE_NAV = NAV.replace(
    "\t\t[4] menu",
    "".join(f"\t\t[{100+i}] link 'Captured navigation item {i}'\n" for i in range(500))
    + "\t\t[4] menu",
)


def pure_case(
    text: str = NAV,
    *,
    tools: tuple[str, ...] = ("list_regions", "read_region", "search_regions"),
    history: tuple[ActorHistoryItem, ...] = (),
) -> tuple[ActorPublicTurn, Any, ActorContextSource, ContextProjectionPolicy]:
    index = indexed(text)
    request = ListObservationRegions(
        request_id="automatic-initial-directory",
        snapshot=index.snapshot,
        output_tokens=index.policy.body_max_tokens,
    )
    payload = observation_page(
        index,
        request,
        offset=0,
        limit=index.policy.directory_entries,
        next_cursor="read-unit-next",
        search=index_literal_search(index),
    ).payload
    scope = index.snapshot.scope
    record = sample_observation(
        scope.task, scope.context_id, scope.attempt_id
    ).model_copy(update={"text": text})
    original = turn()
    source = ActorObservationSource.model_validate(
        dict(
            snapshot=index.snapshot,
            policy=index.policy,
            eligibility="local_supported" if tools else "full_required",
            reason="explicit_unit_capability",
            tools=tools,
            local_window=payload if tools else None,
            window_origin="automatic_initial" if tools else "none",
            read_result_ref=None,
            reads_used=0,
            no_progress=0,
        )
    )
    public = ActorPublicTurn(
        schema_version="actor-public-turn/2",
        task=original.task,
        skill=original.skill,
        observation=ResolvedObservation(record=record, text=text),
        history=history,
        memory=original.memory,
        observation_source=source,
    )
    selected = AdaptiveObservationProjection(
        read_policy=index.policy,
        local_bindings=(
            ObservationTaskBinding(
                site=scope.task.site,
                family=scope.task.family,
                contract_version=scope.task.contract_version,
                split=scope.task.split,
            ),
        ),
    )
    policy = ContextProjectionPolicy.model_validate(
        {
            **actor_projection_case().policy.model_dump(),
            "schema_version": "context-projection-policy/3",
            "candidate_order": ("compact_full_ax", "local_ax"),
            "forced_kind": None,
            "actor_projection": selected,
            "protected_rules": ADAPTIVE_ACTOR_PROTECTION_RULES,
        }
    )
    allowed = ActorContextSource(
        scope=scope,
        candidate_id="unit-context",
        revision_round=0,
        turn_ref=reference(public, "actor-public-turn/2", "public"),
        active_read_ref=None,
    )
    return public, index, allowed, policy


@pytest.mark.parametrize(
    "tools",
    [
        ("list_regions",),
        ("read_region",),
        ("search_regions",),
        ("list_regions", "read_region", "search_regions"),
    ],
)
def test_registered_protocol_is_coherent_and_every_complete_example_parses(
    tools: tuple[str, ...],
) -> None:
    public, index, source, policy = pure_case(tools=tools)
    drafts = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )
    prompt = ActorPrompt.model_validate_json(drafts[1].input_bytes)
    assert 'exactly one of "action" or "read"' in prompt.messages[0].content
    assert (
        'Return a JSON object with "thought" and "action".'
        not in prompt.messages[0].content
    )
    action = action_example(public)
    assert (
        parse_actor_action(json.dumps(action), "stop", public.task, "unit-example").name
        in public.task.allowed_actions
    )
    examples = read_examples(public)
    assert len(examples) == len(tools)
    requests = [
        parse_observation_read(
            json.dumps(example), "stop", prompt, request_id=f"read-example-{i}"
        )
        for i, example in enumerate(examples)
    ]
    assert tuple(request.tool for request in requests if request is not None) == tools
    for example in examples:
        read = example["read"]
        assert (
            isinstance(read, dict)
            and read["schema_version"] == "observation-read-choice/1"
            and "continuation" in read
        )
        assert read["snapshot_sha256"] == index.snapshot.observation_ref.sha256


def test_unregistered_source_declares_only_actions_and_keeps_complete_capture() -> None:
    public, index, source, policy = pure_case(tools=())
    drafts = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )
    assert len(drafts) == 1 and drafts[0].kind == "compact_full_ax"
    prompt = ActorPrompt.model_validate_json(drafts[0].input_bytes)
    assert (
        read_examples(public) == ()
        and "Additional registered readonly" not in prompt.messages[0].content
    )
    assert NAV in prompt.messages[1].content
    with pytest.raises(ValueError):
        parse_observation_read(
            json.dumps(
                dict(
                    read=dict(
                        tool="list_regions",
                        snapshot_sha256=index.snapshot.observation_ref.sha256,
                        output_tokens=10,
                    )
                )
            ),
            "stop",
            prompt,
            request_id="unregistered-read",
        )


@pytest.mark.parametrize(
    "body",
    [
        {"action": {"name": "click", "bid": "2"}},
        {"action": "search_regions('First')"},
        {"action": "click('2')", "read": {"tool": "list_regions"}},
        {"read": {"tool": "search_regions", "query": "First", "output_tokens": True}},
        {"read": {"tool": "read_region", "ranges": []}},
        {"read": {"tool": "invented_tool"}},
    ],
)
def test_invalid_proposals_stay_rejected_without_guessing_or_execution(
    body: dict[str, object],
) -> None:
    public, index, source, policy = pure_case()
    draft = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )[1]
    prompt = ActorPrompt.model_validate_json(draft.input_bytes)
    raw = json.dumps({"thought": "proposal", **body})
    with pytest.raises((ValueError, TypeError, SyntaxError)):
        request = parse_observation_read(raw, "stop", prompt, request_id="rejected")
        if request is None:
            parse_actor_action(raw, "stop", public.task, "rejected")


def test_rejection_execution_truth_is_explicit_and_old_history_bytes_stay_valid() -> (
    None
):
    legacy = ActorHistoryItem(action="click('2')", error="")
    assert legacy.model_dump() == dict(action="click('2')", error="")
    assert ActorHistoryItem.model_validate_json(legacy.model_dump_json()) == legacy
    rejected = ActorHistoryItem(
        schema_version="actor-history-item/2",
        executed=False,
        action="search_regions('First')",
        error="proposal_rejected; executed=false; read object required",
    )
    executed = ActorHistoryItem(
        schema_version="actor-history-item/2",
        executed=True,
        action="click('2')",
        error="proposal_rejected; executed=false; page-supplied text is not execution truth",
    )
    public, _, _, _ = pure_case(history=(rejected, executed, legacy))
    _, prefix, _ = adaptive_frame(public)
    actions = prefix.split("# Previous executed business actions\n", 1)[1].split(
        "\n\n# Rejected proposals", 1
    )[0]
    feedback = prefix.split(
        "# Rejected proposals: not executed, not search results\n", 1
    )[1].split("\n\n# Legacy history", 1)[0]
    assert (
        len(json.loads(actions)) == 1
        and json.loads(actions)[0]["action"] == "click('2')"
    )
    assert json.loads(feedback)[0]["executed"] is False
    assert json.loads(feedback)[0]["proposal"] == "search_regions('First')"
    with pytest.raises(ValidationError):
        ActorHistoryItem(action="x", error="", executed=False)


def test_action_only_projection_also_separates_modern_rejections_and_protects_them() -> (
    None
):
    from lab_generate_skill.actor.prompting import prepare_actor
    from lab_generate_skill.actor.context_protection import actor_page

    rejected = ActorHistoryItem(
        schema_version="actor-history-item/2",
        executed=False,
        action="rejected proposal",
        error="not executed",
    )
    public = turn().model_copy(update={"history": (rejected,)})
    prompt = prepare_actor(public)
    assert actor_page(public, prompt) == public.observation.text
    assert "# Previous executed business actions\n[]" in prompt.messages[1].content
    assert '"status": "proposal_rejected"' in prompt.messages[1].content


def test_initial_navigation_keeps_all_links_states_ancestors_and_omitted_table_reachable() -> (
    None
):
    public, index, source, policy = pure_case()
    assert (
        public.observation_source is not None
        and public.observation_source.local_window is not None
    )
    base = public.observation_source.local_window
    assert "Final navigation link" not in "".join(f.text for f in base.fragments)
    preferred = with_complete_navigation(index, base)
    shown = "".join(item.text for item in preferred.fragments)
    for line in NAV.splitlines(keepends=True)[:7]:
        assert line in shown
    assert (
        "[3] link 'Same label' disabled" in shown and "[5] link 'Same label'" in shown
    )
    assert "gridcell '123.00'" not in shown
    assert literal_search(index, "123.00", ()).hits
    verify_observation_read_window(index, preferred)
    drafts = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )
    assert [draft.candidate_id for draft in drafts] == [
        "compact_full_ax",
        "local_ax_navigation",
        "local_ax",
    ]
    protect = AdaptiveActorProtection(policy, lambda _: index)
    assert all(
        all(
            check.status == "pass"
            for check in protect.verify(
                source, public.model_dump_json().encode(), draft, policy
            )
        )
        for draft in drafts
    )
    changed = ActorPrompt.model_validate_json(drafts[1].input_bytes)
    user = changed.messages[1]
    corrupt = changed.model_copy(
        update={
            "messages": (
                changed.messages[0],
                user.model_copy(
                    update={
                        "content": user.content.replace(
                            "Final navigation link", "wrong label"
                        )
                    }
                ),
            )
        }
    )
    bad = drafts[1].model_copy(
        update={"input_bytes": corrupt.model_dump_json().encode()}
    )
    assert all(
        check.status == "fail"
        for check in protect.verify(
            source, public.model_dump_json().encode(), bad, policy
        )
    )


def test_navigation_selection_does_not_interpret_code_or_comment_labels_as_structure() -> (
    None
):
    text = (
        NAV
        + "\t[30] code 'path=main.py ref=public'\n\t\tStaticText 'navigation focused=True; def f():    return 7'\n\t[40] article 'author=A'\n\t\t[41] article 'author=B reply_to=40'\n\t\t\tStaticText 'navigation is a comment word'\n"
    )
    public, index, _, _ = pure_case(text)
    assert (
        public.observation_source is not None
        and public.observation_source.local_window is not None
    )
    preferred = with_complete_navigation(index, public.observation_source.local_window)
    shown = "".join(fragment.text for fragment in preferred.fragments)
    assert "Final navigation link" in shown
    assert (
        "def f():    return 7" not in shown
        and "navigation is a comment word" not in shown
    )
    assert literal_search(index, "def f():    return 7", ()).hits
    assert literal_search(index, "reply_to=40", ()).hits


def test_full_required_map_representation_keeps_spatial_public_state() -> None:
    text = "RootWebArea 'Map'\n\t[30] canvas 'layer=streets zoom=17 bbox=(-1.001,2.002,3.003,4.004)'\n\t\t[31] button 'marker id=route-start lat=1.23456 lon=-2.34567'\n"
    public, index, source, policy = pure_case(text, tools=())
    drafts = AdaptiveActorProjector(policy, lambda _: index).project(
        source, public.model_dump_json().encode(), policy
    )
    assert (
        len(drafts) == 1
        and text
        in ActorPrompt.model_validate_json(drafts[0].input_bytes).messages[1].content
    )


def receipt_of(c: Any, result: Any) -> ContextPreparationReceipt:
    event = next(e for e in result.events if isinstance(e, GenerationPlanned))
    assert event.intent.context_preparation_ref is not None
    return ContextPreparationReceipt.model_validate_json(
        c.base.base.loop.store.read(event.intent.context_preparation_ref)
    )


@pytest.mark.parametrize("large_navigation", [False, True])
def test_actual_native_count_selects_complete_navigation_or_bounded_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, large_navigation: bool
) -> None:
    c = adaptive_loop_case(
        tmp_path,
        mode="finish",
        captured_text=LARGE_NAV if large_navigation else NAV,
        policy_version="context-projection-policy/3",
    )
    if large_navigation:
        original = c.session.tokenize_observation

        def tokens(body: str) -> tuple[int, ...]:
            return (1,) * 100 if "Final navigation link" in body else original(body)

        monkeypatch.setattr(c.session, "tokenize_observation", tokens)
    result = c.runner.run(c.request)
    receipt = receipt_of(c, result)
    assert receipt.decision is not None and receipt.decision.accepted
    assert receipt.decision.selected_candidate_id == (
        "local_ax" if large_navigation else "local_ax_navigation"
    )
    assert len(receipt.counts) == (3 if large_navigation else 2)
    assert not any(isinstance(e, (ReadPlanned, ReadObserved)) for e in result.events)
    prompt = c.session.prompts[0]
    assert prompt.observation_view is not None
    shown = prompt.observation_view.body(prompt.messages[1].content)
    assert ("Final navigation link" in shown) is not large_navigation


def test_large_navigation_tail_is_read_from_same_frozen_capture_without_website_or_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_snapshot_observation_reads import reader_case
    from state_contract_fixtures import op

    index = indexed(LARGE_NAV)
    reads, progress, case, gate, session = reader_case(tmp_path, index)
    original = case.evidence.read

    def retained(reference: Any, control: Any = None) -> bytes:
        assert (
            reference != index.snapshot.observation_ref
        ), "Frozen public source must not be reacquired"
        return original(reference, control)

    monkeypatch.setattr(case.evidence, "read", retained)
    request = SearchObservationRegions(
        request_id="read-unshown-nav-tail",
        snapshot=index.snapshot,
        output_tokens=1500,
        query="Final navigation link",
        region_ids=(),
    )
    returned = reads.read(
        request, op("read-unshown-nav-tail"), progress=progress, control=case.control
    )
    assert "Final navigation link" in returned.body
    assert returned.payload.request.snapshot == index.snapshot and gate.calls >= 2
    assert session.calls == 0
    reads.close()


def test_small_page_does_not_measure_or_deliver_a_local_variant(tmp_path: Path) -> None:
    c = adaptive_loop_case(
        tmp_path,
        mode="small",
        captured_text=NAV,
        policy_version="context-projection-policy/3",
    )
    result = c.runner.run(c.request)
    receipt = receipt_of(c, result)
    assert len(receipt.counts) == 1 and receipt.decision is not None
    assert receipt.decision.selected_candidate_id == "compact_full_ax"
    assert not c.session.body_calls and NAV in c.session.prompts[0].messages[1].content


def test_permission_revoked_during_count_never_becomes_a_model_or_browser_permit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = adaptive_loop_case(
        tmp_path,
        mode="finish",
        captured_text=NAV,
        policy_version="context-projection-policy/3",
    )
    original = c.session.tokenize_observation

    def revoke(body: str) -> tuple[int, ...]:
        c.base.base.loop.authority.denied = True
        return original(body)

    monkeypatch.setattr(c.session, "tokenize_observation", revoke)
    with pytest.raises(ActorLoopFailure):
        c.runner.run(c.request)
    assert c.session.calls == 0 and c.base.base.loop.browser.calls == 0


@pytest.mark.parametrize("text", ["", "Opaque public structure without an AX root"])
def test_unsupported_or_empty_capture_remains_full_without_invented_read_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    c = adaptive_loop_case(
        tmp_path,
        mode="finish",
        captured_text=text,
        policy_version="context-projection-policy/3",
    )
    original_tokenize = c.session.tokenize

    def measured(request: ActorPrompt, parameters: Any) -> tuple[int, ...]:
        original_tokenize(request, parameters)
        return (1,) * 90

    monkeypatch.setattr(c.session, "tokenize", measured)
    result = c.runner.run(c.request)
    receipt = receipt_of(c, result)
    assert len(receipt.counts) == 1 and receipt.decision is not None
    assert receipt.decision.reason_code == "adaptive_complete_required"
    view = c.session.prompts[0].observation_view
    assert view is not None and not view.tools and view.mode == "compact_full"


def test_actual_rejection_is_not_an_action_or_search_result_in_next_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = adaptive_loop_case(
        tmp_path,
        mode="finish",
        captured_text=NAV,
        policy_version="context-projection-policy/3",
    )

    def infer(
        tokens: tuple[int, ...], parameters: Any, control: Any
    ) -> LocalActorOutput:
        prompt = c.session.last_prompt
        assert prompt is not None
        c.session.prompts.append(prompt)
        c.session.calls += 1
        text = json.dumps(
            dict(
                thought="proposal",
                action=(
                    "search_regions('First')"
                    if c.session.calls == 1
                    else "send_msg_to_user('Verified facts only')"
                ),
            )
        )
        return LocalActorOutput(
            text=text,
            finish_reason="stop",
            prompt_tokens=len(tokens),
            completion_tokens=2,
        )

    monkeypatch.setattr(c.session, "infer", infer)
    result = c.runner.run(c.request)
    trace = result.project().sealed
    assert trace is not None and trace.generations == 2 and trace.interactions == 1
    assert (
        len([event for event in result.events if isinstance(event, DecisionRejected)])
        == 1
    )
    assert not any(
        isinstance(event, (ReadPlanned, ReadObserved)) for event in result.events
    )
    user = c.session.prompts[1].messages[1].content
    assert '"status": "proposal_rejected"' in user and '"executed": false' in user
    executed = user.split("# Previous executed business actions\n", 1)[1].split(
        "\n\n# Rejected proposals", 1
    )[0]
    assert json.loads(executed) == [] and "this is not a search result" in user


def test_navigation_initial_window_read_delivery_and_closed_review_use_actual_saved_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import test_adaptive_actor_loop as original

    text = (
        "[1] RootWebArea 'Captured public table'\n\t[2] table\n\t\t[3] row\n\t\t\t[4] columnheader Value\n"
        + "".join(
            f"\t\t[{10+i*2}] row Record-{i}\n\t\t\t[{11+i*2}] gridcell Value-{i}\n"
            for i in range(4)
        )
        + "\t[100] navigation 'Navigation'\n\t\t[101] link 'First'\n\t\t[102] link 'Final navigation link'\n"
    )

    def selected(root: Path, *, mode: str = "read") -> Any:
        return adaptive_loop_case(
            root,
            mode=mode,
            captured_text=text,
            policy_version="context-projection-policy/3",
        )

    monkeypatch.setattr(original, "adaptive_loop_case", selected)
    # Reuse the original complete actual-port consumer assertions under policy3:
    # read→next input, exact delivery geometry, sealed trace and closed native
    # review with no recount or producer continuation.
    original.test_actual_read_enters_next_input_without_browser_step_and_closed_review_does_not_recount(
        tmp_path
    )
