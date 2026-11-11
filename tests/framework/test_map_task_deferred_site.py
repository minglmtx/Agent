"""Same frozen task entry with late original site; no real source/model calls."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from lab_generate_skill.ports.lifecycle import OperationControl
from map_navigation_group_cases import SOURCES
from map_navigation_evaluation_fixtures import closed_review
from map_task_execution_current_fixtures import (
    current_map_execution_case,
    UnitCurrentMapExecutionAuthority,
)
from map_task_execution_review_fixtures import current_map_review_facts
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("source_id", SOURCES)
def test_complete_subgroup_original_acquiring_to_reset_then_site_close(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    with current_map_execution_case(
        node_path, monkeypatch, source_id, deferred_site=True
    ) as case:
        p, b = case.p, case.bundle
        assert isinstance(p.site, RetainedSiteResource)
        assert p.original.resource.channels == [] and p.original.worker is None
        assert case.task_source._native is None
        original_plan = p.plan.model_dump_json()
        original_open = p.site.open
        seen: list[str] = []

        def opened(control: OperationControl) -> Any:
            snapshot = case.journals.runs.read(p.plan.read_operation)
            seen.append(snapshot.project()[1][0].stage)
            return original_open(control)

        monkeypatch.setattr(p.site, "open", opened)
        result = b.task.execute(p.plan.intent, p.plan.operation)
        assert seen == ["acquiring"] and p.plan.model_dump_json() == original_plan
        assert (
            result.evaluation.status == "success"
            and result.generations == result.interactions == 1
        )
        assert p.site.phase == "closed" and p.site.closed is not None
        assert case.task_source._native is b.native_authority
        assert (
            b.finalization.state.reset is not None
            and b.finalization.state.reset.status == "safe"
        )
        assert [x.action for x in p.requests] == ["snapshot", "prepare", "restore"]
        assert len(p.original.resource.channels) == 1
        facts = current_map_review_facts(case, result)
        before = case.native.loader.session.calls
        with pytest.raises(DispatchAlreadyCommitted):
            b.task.execute(p.plan.intent, p.plan.operation)
        assert case.native.loader.session.calls == before and seen == ["acquiring"]
        original = p.original
    closed_review(original, facts)


def test_late_source_denial_prevents_any_site_or_actor_effect(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_map_execution_case(
        node_path, monkeypatch, SOURCES[0], deferred_site=True
    ) as case:
        assert isinstance(
            case.bundle.task.deps.authority, UnitCurrentMapExecutionAuthority
        )
        case.bundle.task.deps.authority.denied = True
        with pytest.raises((PermissionError, TaskExecutionUnconfirmed)):
            case.bundle.task.execute(case.p.plan.intent, case.p.plan.operation)
        assert case.p.original.resource.channels == []
        assert case.native.loader.session.calls == 0 and case.p.requests == []
        assert (
            isinstance(case.p.site, RetainedSiteResource) and case.p.site.closed is None
        )


def test_model_unknown_closes_actual_site_after_original_restore_without_replay(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_map_execution_case(
        node_path, monkeypatch, SOURCES[0], deferred_site=True
    ) as case:
        original = case.native.client.generate_exchange

        def lost(*args: Any, **kwargs: Any) -> Any:
            original(*args, **kwargs)
            raise TimeoutError("controlled original model return lost")

        monkeypatch.setattr(case.native.client, "generate_exchange", lost)
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            case.bundle.task.execute(case.p.plan.intent, case.p.plan.operation)
        assert caught.value.evaluation is None and caught.value.cleanup_errors == ()
        assert (
            case.bundle.finalization.state.reset is not None
            and case.bundle.finalization.state.reset.status == "safe"
        )
        assert (
            isinstance(case.p.site, RetainedSiteResource)
            and case.p.site.phase == "closed"
        )
        assert [x.action for x in case.p.requests] == ["snapshot", "prepare", "restore"]
        with pytest.raises(DispatchAlreadyCommitted):
            case.bundle.task.execute(case.p.plan.intent, case.p.plan.operation)
        assert case.native.loader.session.calls == 1


def test_late_site_keeps_valid_failure_and_original_independent_closed_review(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_map_execution_case(
        node_path, monkeypatch, SOURCES[0], deferred_site=True, negative=True
    ) as case:
        result = case.bundle.task.execute(case.p.plan.intent, case.p.plan.operation)
        assert result.evaluation.status == "failure" and result.evaluation.reward == 0
        assert (
            isinstance(case.p.site, RetainedSiteResource)
            and case.p.site.phase == "closed"
        )
        facts = current_map_review_facts(case, result)
        original = case.p.original
    closed_review(original, facts)


def test_resource_close_unconfirmed_keeps_known_result_and_refuses_normal_return(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with current_map_execution_case(
        node_path, monkeypatch, SOURCES[0], deferred_site=True
    ) as case:
        # Explicit unit source denies whole-resource closure after native
        # recovery. No success is returned/exported despite known judgment.
        case.p.original.resource.authority.deny = "closed"
        with pytest.raises(BaseExceptionGroup) as caught:
            case.bundle.task.execute(case.p.plan.intent, case.p.plan.operation)
        known = getattr(caught.value, "known_task_result", None)
        assert known is not None and known.intent == case.p.plan.intent
        assert known.evaluation.status == "success"
        reset = case.bundle.finalization.state.reset
        assert reset is not None and reset.status == "safe"
        assert isinstance(case.p.site, RetainedSiteResource)
        assert case.p.site.closed is None and case.p.site.phase == "close-unconfirmed"
        assert case.native.loader.session.calls == 1
        assert case.p.original.resource.channels[0].capture.termination is not None
