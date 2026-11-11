"""Confirmed preparation/closure references cannot be substituted for recovery."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites.task_finalization import (
    TaskFinalizationUnconfirmed,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from task_capture_port_fixtures import capture_case
from task_finalization_port_fixtures import bind_finalization


@pytest.mark.parametrize(
    "fault", ["prepare-body", "prepare-parent", "result-digest", "result-type"]
)
def test_tampered_confirmed_preparation_never_reaches_native_restore(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        f = bind_finalization(case)
        f.close()
        p = case.initial.preparation
        s, store = p.preparation.state, p.original.resource.evidence
        assert s.prepare_request is not None and s.prepare_result is not None
        if fault == "prepare-body":
            s.prepare_request = s.prepare_request.model_copy(
                update={"action": "snapshot"}
            )
        elif fault == "prepare-parent":
            s.prepare_request = s.prepare_request.model_copy(
                update={
                    "operation": s.prepare_request.operation.model_copy(
                        update={"operation_id": "foreign-prepare"}
                    )
                }
            )
            s.prepare_request_ref = put(store, s.prepare_request)
        elif fault == "result-digest":
            s.prepare_result = s.prepare_result.model_copy(
                update={"request_sha256": "f" * 64}
            )
            s.prepare_result_ref = put(store, s.prepare_result)
        else:
            s.prepare_result_ref = put(store, p.reset)
        with pytest.raises(TaskFinalizationUnconfirmed) as caught:
            f.restore()
        assert isinstance(caught.value.primary, (OwnershipConflict, ValueError))
        assert [r.action for r in p.requests] == ["snapshot", "prepare"]
        assert f.resume.calls == 0 and f.finalizer.state.reset_ref is None
        with pytest.raises(DispatchAlreadyCommitted):
            f.restore()


def test_foreign_known_closure_is_rejected_after_original_physical_exit(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with capture_case(node_path, monkeypatch) as case:
        case.initial.start()
        f = bind_finalization(case)
        p = case.initial.preparation
        foreign = put(p.original.resource.evidence, p.reset)
        monkeypatch.setattr(f.finalizer.browser, "known_closure", lambda: foreign)
        with pytest.raises(TaskFinalizationUnconfirmed) as caught:
            f.close()
        assert isinstance(caught.value.primary, OwnershipConflict)
        assert case.initial.browser.phase == "closed"
        assert case.initial.backend.resource.channels[0].finishes == 1
        assert f.finalizer.state.closed is None and f.finalizer.state.reset_ref is None
        assert f.finalizer.browser.references and f.resume.calls == 0
        with pytest.raises(DispatchAlreadyCommitted):
            f.close()
