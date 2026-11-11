"""Current producer, original native RPC/CAS and retained fixed browser seam."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from map_navigation_group_cases import SOURCES
from site_instance_fixtures import node_path as node_path
from task_initialization_port_fixtures import initialization_case


@pytest.mark.parametrize("source_id", SOURCES)
def test_original_first_return_produces_baseline_equivalence_and_actor2(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    with initialization_case(node_path, monkeypatch, source_id) as case:
        result = case.start()
        state = case.initialization.state
        assert state.phase == "initialized"
        assert state.baseline is not None and state.baseline.status == "ready"
        assert (
            state.equivalence is not None and state.equivalence.status == "equivalent"
        )
        assert result.actor.schema_version == "actor-run-request/2"
        assert (
            result.actor.initial_observation_ref == case.browser.session.observation_ref
        )
        assert result.actor.task == case.preparation.source.native.public
        assert result.actor.operation == case.preparation.plan.operation
        assert case.browser.phase == "open"
        assert (
            len(case.backend.engines) == 1 and case.backend.calls.count("project") == 1
        )
        assert [r.action for r in case.preparation.requests] == ["snapshot", "prepare"]
        with pytest.raises(DispatchAlreadyCommitted):
            case.start()
        assert case.backend.calls.count("project") == 1

    assert case.browser.phase == "closed"
    assert case.browser.closed is not None and case.browser.closed.state == "closed"


@pytest.mark.parametrize(
    "gate", ["initialization", "historical-context", "historical-state", "capture"]
)
def test_denied_initialization_never_replays_and_retains_owned_browser(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    with initialization_case(node_path, monkeypatch) as case:
        if gate == "initialization":
            case.authority.denied = True
        elif gate == "historical-context":
            case.context_authority.denied_context = True
        elif gate == "historical-state":
            case.context_authority.denied = True
        else:
            case.capture_authority.denied = True
        with pytest.raises(TaskInitializationUnconfirmed) as caught:
            case.start()
        assert case.initialization.state.phase == "quarantined"
        assert caught.value.primary is not None
        assert case.browser.phase == ("open" if gate == "capture" else "new")
        assert len(case.backend.engines) == (1 if gate == "capture" else 0)
        if gate == "capture":
            assert caught.value.references
            assert any(
                r.content_schema == "browser-capture-intent/1"
                for r in caught.value.references
            )
        with pytest.raises(DispatchAlreadyCommitted):
            case.start()
