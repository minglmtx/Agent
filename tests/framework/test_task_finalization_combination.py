"""All8 new finalization joins; no original business attempt is replayed."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites import step as site_step
from lab_generate_skill.adapters.browsergym import step as browser_step
from map_navigation_group_cases import SOURCES
from map_navigation_evaluation_fixtures import closed_review
from map_closed_review_fixtures import closed_proof
from site_instance_fixtures import node_path as node_path
from task_capture_port_fixtures import capture_case
from task_finalization_review_fixtures import finalized_facts


@pytest.mark.parametrize("source_id", SOURCES)
def test_complete_navigation_original_judgment_new_finalization_closed_review(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    with capture_case(node_path, monkeypatch, source_id) as case:
        closed_proof(site_step, monkeypatch)
        closed_proof(browser_step, monkeypatch)
        case.actor()
        case.collect()
        result = finalized_facts(case)
        assert result["expected_status"] == "success"
        original = case.initial.preparation.original
    closed_review(original, result)


def test_valid_business_failure_still_restores_and_reviews_without_relabeling(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with capture_case(node_path, monkeypatch, negative=True) as case:
        closed_proof(site_step, monkeypatch)
        closed_proof(browser_step, monkeypatch)
        case.actor()
        case.collect()
        result = finalized_facts(case)
        assert result["expected_status"] == "failure"
        original = case.initial.preparation.original
    closed_review(original, result)
