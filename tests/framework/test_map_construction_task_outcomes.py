"""Original control completion on valid negative, unknown and duplicate waiting."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.construct_targets import (
    construct_targets,
    ConstructionStepUnconfirmed,
)
from lab_generate_skill.bootstrap.construction_task_execution import (
    ConstructionTaskFactoryUnconfirmed,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from map_construction_task_factory_fixtures import original_map_control_case
from map_navigation_evaluation_fixtures import closed_review
from map_navigation_group_cases import SOURCES
from map_task_execution_review_fixtures import current_map_review_facts
from site_instance_fixtures import node_path as node_path


def test_original_control_records_valid_failure_without_relabel_or_rerun(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with original_map_control_case(
        node_path, monkeypatch, SOURCES[0], negative=True
    ) as c:
        result = construct_targets(c.saved.step, c.deps)
        actual = result.progress.project().attempts[-1]
        assert actual.evaluation.status == "failure" and actual.evaluation.reward == 0
        assert c.calls == [actual.intent] and c.actual.native.loader.session.calls == 1
        assert (
            isinstance(c.actual.p.site, RetainedSiteResource)
            and c.actual.p.site.phase == "closed"
        )
        facts = current_map_review_facts(c.actual, actual)
        original = c.actual.p.original
    closed_review(original, facts)


def test_original_control_model_unknown_keeps_pending_and_never_reinvokes(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with original_map_control_case(node_path, monkeypatch, SOURCES[0]) as c:
        actual = c.actual
        original_generate = actual.native.client.generate_exchange

        def lost(*args: Any, **kwargs: Any) -> Any:
            original_generate(*args, **kwargs)
            raise TimeoutError("original unit model return lost; no replay")

        monkeypatch.setattr(actual.native.client, "generate_exchange", lost)
        with pytest.raises(ConstructionStepUnconfirmed) as caught:
            construct_targets(c.saved.step, c.deps)
        error = caught.value
        assert error.phase == "original_actor_lifecycle" and error.response is None
        assert isinstance(error.primary, ConstructionTaskFactoryUnconfirmed)
        assert error.primary.phase == "original_task"
        assert isinstance(error.primary.primary, TaskExecutionUnconfirmed)
        assert error.primary.primary.evaluation is None
        assert error.primary.primary.cleanup_errors == ()
        assert error.progress.project().pending_attempt == actual.p.plan.intent
        assert (
            actual.bundle.finalization.state.reset is not None
            and actual.bundle.finalization.state.reset.status == "safe"
        )
        assert (
            isinstance(actual.p.site, RetainedSiteResource)
            and actual.p.site.phase == "closed"
        )
        waiting = construct_targets(c.saved.step, c.deps)
        assert (
            waiting.status == "waiting"
            and waiting.progress.project().pending_attempt == actual.p.plan.intent
        )
        assert (
            c.calls == [actual.p.plan.intent]
            and actual.native.loader.session.calls == 1
        )
