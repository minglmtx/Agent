"""Complete selected subgroup consumes the original construction control entry.

All source/physical/model/page permissions remain explicit software premises.
"""

from pathlib import Path
import pytest
from lab_generate_skill.application.construct_targets import construct_targets
from lab_generate_skill.bootstrap.construction_task_execution import (
    RecordedConstructionTasks,
)
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from map_construction_task_factory_fixtures import original_map_control_case
from map_task_execution_review_fixtures import current_map_review_facts
from map_navigation_evaluation_fixtures import closed_review
from map_navigation_group_cases import SOURCES
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("source_id", SOURCES)
def test_complete_group_original_control_pure_factory_task_result_and_closed_review(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    with original_map_control_case(node_path, monkeypatch, source_id) as control:
        case, deps, saved, seen = (
            control.actual,
            control.deps,
            control.saved,
            control.calls,
        )
        p = case.p
        result = construct_targets(saved.step, deps)
        assert (
            result.status == "advanced"
            and result.progress.project().pending_attempt is None
        )
        completed = result.progress.project().attempts[-1]
        assert (
            completed.intent == p.plan.intent
            and completed.evaluation.status == "success"
        )
        assert isinstance(deps.attempts, RecordedConstructionTasks)
        assert seen == [p.plan.intent] and case.native.loader.session.calls == 1
        assert isinstance(p.site, RetainedSiteResource) and p.site.phase == "closed"
        original_result = completed
        facts = current_map_review_facts(case, original_result)
        original = p.original
    closed_review(original, facts)
