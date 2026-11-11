"""Actual current preparation/Actor2/capture with new original cleanup producer."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from map_navigation_group_cases import SOURCES
from site_instance_fixtures import node_path as node_path
from task_capture_port_fixtures import capture_case
from task_finalization_port_fixtures import bind_finalization


@pytest.mark.parametrize("source_id", SOURCES)
def test_original_closed_browser_is_only_read_then_full_restore_once(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    with capture_case(node_path, monkeypatch, source_id) as case:
        case.actor()
        case.collect()
        f = bind_finalization(case)
        b = case.initial.backend.resource
        finishes = b.channels[0].finishes
        closed = f.close()
        assert closed.closure_refs == (case.capture.state.closure_ref,)
        assert b.channels[0].finishes == finishes
        ref = f.restore()
        assert (
            f.finalizer.state.reset is not None
            and f.finalizer.state.reset.status == "safe"
        )
        assert (
            f.finalizer.state.reset_ref == ref and f.finalizer.state.phase == "restored"
        )
        assert f.resume.calls == 1 and f.unstarted.calls == 0
        assert [r.action for r in case.initial.preparation.requests] == [
            "snapshot",
            "prepare",
            "restore",
        ]
        with pytest.raises(DispatchAlreadyCommitted):
            f.close()
        with pytest.raises(DispatchAlreadyCommitted):
            f.restore()
        assert f.resume.calls == 1 and b.channels[0].finishes == finishes
