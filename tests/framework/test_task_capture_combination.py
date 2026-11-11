"""Complete8 new capture with original v2 Actor/guard/judgment/restore/new process."""

from pathlib import Path
import pytest
from map_navigation_group_cases import SOURCES
from map_navigation_evaluation_fixtures import closed_review
from map_closed_review_fixtures import closed_proof
from lab_generate_skill.adapters.sites import step as site_step
from lab_generate_skill.adapters.browsergym import step as browser_step
from site_instance_fixtures import node_path as node_path
from task_capture_port_fixtures import capture_case
from task_capture_restore_fixtures import restore_facts


@pytest.mark.parametrize("source_id", SOURCES)
def test_complete_navigation_consumer_new_capture_original_restore_and_closed_review(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    with capture_case(node_path, monkeypatch, source_id) as case:
        closed_proof(site_step, monkeypatch)
        closed_proof(browser_step, monkeypatch)
        case.actor()
        case.collect()
        facts = restore_facts(case)
        assert facts["expected_status"] == "success"
        assert facts["qualified_source"]["reset_status"] == "safe"
        assert case.site_authority.calls == 1
        original = case.initial.preparation.original
    closed_review(original, facts)
