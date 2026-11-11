"""Resume denial preserves completed restore and never manufactures safe Reset."""

from pathlib import Path
from typing import Any
import os
import threading
import pytest
from lab_generate_skill.adapters.sites.task_site_resume_authority import (
    OriginalTaskSiteResumeAuthority,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.lifecycle import OperationControl
from map_navigation_browser_fixtures import CancelledControl
from map_navigation_group_cases import SOURCES
from map_task_execution_current_fixtures import current_map_execution_case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize("fault", ["restore", "intent-producer", "closure", "cancel"])
def test_default_resume_denies_wrong_lineage_or_cancel_without_safe_reset(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as case:
        p, bundle = case.p, case.bundle
        authority = bundle.finalization.resume_authority
        assert isinstance(authority, OriginalTaskSiteResumeAuthority)
        original = authority.verify_resume
        calls: list[str] = []

        def verify(
            configuration: SiteWorkerConfiguration,
            request: SiteResumeRequest,
            intent_ref: EvidenceRef,
            control: OperationControl,
        ) -> None:
            calls.append(fault)
            if fault == "restore":
                request = request.model_copy(
                    update={
                        "restore_result_ref": request.restore_result_ref.model_copy(
                            update={"sha256": "0" * 64}
                        )
                    }
                )
            elif fault == "intent-producer":
                intent_ref = intent_ref.model_copy(update={"producer": "other"})
            elif fault == "closure":
                bundle.finalization.state.closed = None
            elif fault == "cancel":
                control = CancelledControl()
            original(configuration, request, intent_ref, control)

        monkeypatch.setattr(authority, "verify_resume", verify)
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            bundle.task.execute(p.plan.intent, p.plan.operation)
        assert calls == [fault] and not authority.consumed
        assert caught.value.cleanup_errors and bundle.finalization.state.reset is None
        assert (
            bundle.finalization.state.restore_attempted
            and bundle.finalization.state.restore_result is not None
        )
        assert (
            bundle.finalization.state.resume_result_ref is None
            and case.native.loader.session.calls == 1
        )
        assert [r.action for r in p.requests] == ["snapshot", "prepare", "restore"]


@pytest.mark.parametrize("value", [None, {}, [], "", False, 1])
def test_bad_resume_shape_never_obtains_finalizer_or_permission(value: Any) -> None:
    receiver = object.__new__(OriginalTaskSiteResumeAuthority)
    receiver.owner = os.getpid(), threading.get_ident()
    receiver.consumed = False
    with pytest.raises((ValueError, TypeError)):
        receiver.verify_resume(value, value, value, guard())
    assert not receiver.consumed
