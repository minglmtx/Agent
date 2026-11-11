"""Same original init/Actor2/trace -> capture/closed browser/native guard/judgment."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from map_navigation_group_cases import SOURCES
from site_instance_fixtures import node_path as node_path
from task_capture_port_fixtures import capture_case


@pytest.mark.parametrize("source_id", SOURCES)
def test_original_initialized_actor2_terminal_guard_and_judgment(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    with capture_case(node_path, monkeypatch, source_id) as case:
        snapshot = case.actor()
        captured = case.collect()
        p = case.initial.preparation
        assert captured.contract == p.plan.evaluation
        assert snapshot.project().sealed is not None
        assert case.capture.state.phase == "captured"
        assert case.initial.browser.phase == "closed"
        assert case.site_authority.calls == 1
        assert case.initial.backend.calls.count("actual_action") == 1
        assert case.initial.backend.calls.count("project") == 2
        evaluated = case.evaluator.evaluate(
            p.plan.evaluation,
            p.original.resource.evidence,
            p.original.resource.controls.bind(p.plan.operation),
        )
        assert evaluated.status == "success" and evaluated.reward == 1
        with pytest.raises(DispatchAlreadyCommitted):
            case.collect()
        assert case.site_authority.calls == 1


def test_valid_negative_keeps_original_failure_without_another_actor(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with capture_case(node_path, monkeypatch, negative=True) as case:
        case.actor()
        case.collect()
        p = case.initial.preparation
        evaluated = case.evaluator.evaluate(
            p.plan.evaluation,
            p.original.resource.evidence,
            p.original.resource.controls.bind(p.plan.operation),
        )
        assert evaluated.status == "failure" and evaluated.reward == 0
        assert case.initial.backend.calls.count("actual_action") == 1
