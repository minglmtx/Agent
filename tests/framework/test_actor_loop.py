"""Bounded loop composition; synthetic engines never count as actual Actor runs."""

from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.application.actor_loop import ActorLoopFailure
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.errors import OwnershipConflict
from test_run_journal import command
from actor_loop_fixtures import case


def test_fresh_loop_uses_original_view_two_real_returns_and_seals(
    tmp_path: Path,
) -> None:
    c = case(tmp_path)
    final = c.runner.run(c.request)
    trace = final.project().sealed
    assert trace is not None and trace.stop_reason == "finished"
    assert (
        trace.generations == c.model.calls == trace.interactions == c.browser.calls == 2
    )
    assert trace.initial_observation_ref == c.request.initial_observation_ref
    assert "Saved public state" in c.model.prompts[1].messages[1].content
    assert "click('2')" in c.model.prompts[1].messages[1].content
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert isinstance(caught.value.primary, OwnershipConflict)
    assert c.model.calls == c.browser.calls == 2


def test_invalid_response_counts_generation_but_not_interaction(tmp_path: Path) -> None:
    c = case(tmp_path, ("not JSON", '{"action":"send_msg_to_user(\'Done\')"}'))
    final = c.runner.run(c.request).project().sealed
    assert final is not None and final.generations == 2 and final.interactions == 1
    assert c.model.calls == 2 and c.browser.calls == 1
    assert "not JSON" in c.model.prompts[1].messages[1].content


@pytest.mark.parametrize(
    "responses,reason",
    [
        (("invalid",), "generation_limit"),
        (('{"action":"click(\'2\')"}',), "interaction_limit"),
    ],
)
def test_exact_independent_limits_stop_without_extra_call(
    tmp_path: Path, responses: tuple[str, ...], reason: str
) -> None:
    c = case(tmp_path, responses)
    trace = c.runner.run(c.request).project().sealed
    assert trace is not None and trace.stop_reason == reason
    if reason == "generation_limit":
        assert c.model.calls == c.journal.plan.max_generations and c.browser.calls == 0
    else:
        assert (
            c.browser.calls == c.journal.plan.max_interactions
            and c.model.calls == c.browser.calls
        )


@pytest.mark.parametrize(
    "status,reason", [("failed", "error"), ("uncertain", "uncertain")]
)
def test_actual_model_failure_fact_seals_without_browser(
    tmp_path: Path, status: str, reason: str
) -> None:
    c = case(tmp_path)
    c.model.status = status
    trace = c.runner.run(c.request).project().sealed
    assert trace is not None and trace.stop_reason == reason and trace.generations == 1
    assert c.model.calls == 1 and c.browser.calls == 0


@pytest.mark.parametrize("where", ["model", "browser"])
def test_unknown_effect_leaves_original_intent_unsealed_and_never_replays(
    tmp_path: Path, where: str
) -> None:
    c = case(tmp_path)
    target = c.model if where == "model" else c.browser
    target.failure = TimeoutError("actual outcome unavailable")
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    snapshot = caught.value.snapshot
    assert snapshot is not None and snapshot.project().sealed is None
    assert snapshot.project().intent is not None
    assert (snapshot.project().action is not None) == (where == "browser")
    with pytest.raises(ActorLoopFailure):
        c.runner.run(c.request)
    assert c.model.calls == 1 and c.browser.calls == int(where == "browser")


def test_denied_live_authority_has_no_model_or_browser_effect(tmp_path: Path) -> None:
    c = case(tmp_path)
    c.authority.denied = True
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert isinstance(caught.value.primary, PermissionError)
    assert c.model.calls == c.browser.calls == 0
    assert c.journal.read(command(attempt="attempt")).revision == 0


@pytest.mark.parametrize(
    "change",
    [
        "scope",
        "model_kind",
        "browser_attempt",
        "parameters_count",
        "initial_observation",
        "enabled_memory",
        "cleanup",
        "seconds",
        "old_version",
    ],
)
def test_wrong_request_refused_without_external_effect(
    tmp_path: Path, change: str
) -> None:
    c = case(tmp_path)
    data = c.request.model_dump()
    if change == "scope":
        data["scope"]["attempt_id"] = "other"
    if change == "model_kind":
        data["model_allocation"]["resource_kind"] = "generator"
    if change == "browser_attempt":
        data["browser_allocation"]["attempt_id"] = "other"
    if change == "parameters_count":
        data["parameters_refs"] = data["parameters_refs"][:1]
    if change == "initial_observation":
        data["initial_observation_ref"]["producer"] = "other"
    if change == "enabled_memory":
        data["memory"]["status"] = "enabled"
    if change == "cleanup":
        data["operation"].update(mode="cleanup", parent_operation_id="other")
    if change == "seconds":
        data["generation_seconds"] = True
    if change == "old_version":
        data["schema_version"] = "actor-run-request/0"
    with pytest.raises((ValueError, ActorLoopFailure)):
        c.runner.run(cast(ActorRunRequest, data))
    assert c.model.calls == c.browser.calls == 0
