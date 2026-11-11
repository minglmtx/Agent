"""Original current native guard consumes production producer/intent/closure checks."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_site_capture_authority import (
    OriginalTaskSiteCaptureAuthority,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.ports.lifecycle import OperationControl
from map_navigation_group_cases import SOURCES
from map_task_execution_current_fixtures import current_map_execution_case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "collector",
        "operation",
        "snapshot",
        "intent-producer",
        "missing-browser-close",
        "phase",
    ],
)
def test_real_current_producer_rejects_wrong_guard_before_wire_and_recovers(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as case:
        bundle, p = case.bundle, case.p
        authority = bundle.capture.site_authority
        assert isinstance(authority, OriginalTaskSiteCaptureAuthority)
        original = authority.verify_capture
        injected: list[str] = []

        def verify(
            configuration: SiteWorkerConfiguration,
            request: SiteCaptureRequest,
            intent_ref: EvidenceRef,
            control: OperationControl,
        ) -> None:
            injected.append(fault)
            if fault == "collector":
                request = request.model_copy(update={"collector_id": "unknown"})
            elif fault == "operation":
                inspection = request.inspection.model_copy(
                    update={
                        "operation": request.operation.model_copy(
                            update={"operation_id": "other-guard"}
                        )
                    }
                )
                request = request.model_copy(update={"inspection": inspection})
            elif fault == "snapshot":
                request = request.model_copy(
                    update={
                        "inspection": request.inspection.model_copy(
                            update={"snapshot_ref": None}
                        )
                    }
                )
            elif fault == "intent-producer":
                intent_ref = intent_ref.model_copy(update={"producer": "other"})
            elif fault == "missing-browser-close":
                bundle.capture.state.closure_ref = None
            elif fault == "phase":
                bundle.capture.state.phase = "captured"
            original(configuration, request, intent_ref, control)

        monkeypatch.setattr(authority, "verify_capture", verify)
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            bundle.task.execute(p.plan.intent, p.plan.operation)
        assert injected == [fault]
        assert caught.value.primary is not None and not authority.consumed
        assert bundle.capture.state.selection_ref is None
        assert bundle.finalization.state.reset is not None
        assert bundle.finalization.state.reset.status == "safe"
        assert case.native.loader.session.calls == 1
        with pytest.raises(DispatchAlreadyCommitted):
            bundle.task.execute(p.plan.intent, p.plan.operation)
        assert case.native.loader.session.calls == 1


@pytest.mark.parametrize("value", [None, {}, [], "", False, 1])
def test_bad_request_type_does_not_acquire_source_or_capture(value: Any) -> None:
    # Shape failure occurs before producer access; construct only the receiver's
    # owner-local identity, never grant a source or create a usable capability.
    import os
    import threading

    receiver = object.__new__(OriginalTaskSiteCaptureAuthority)
    receiver.owner = os.getpid(), threading.get_ident()
    receiver.consumed = False
    with pytest.raises((ValueError, TypeError)):
        receiver.verify_capture(value, value, value, guard())
    assert receiver.consumed is False


def test_default_capture_and_resume_consume_same_original_intents_once(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lab_generate_skill.adapters.sites.task_site_resume_authority import (
        OriginalTaskSiteResumeAuthority,
    )
    from lab_generate_skill.domain.site_capture import SiteCaptureIntent
    from lab_generate_skill.domain.site_resume import SiteResumeIntent

    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as case:
        p, bundle = case.p, case.bundle
        result = bundle.task.execute(p.plan.intent, p.plan.operation)
        capture, resume = (
            bundle.capture.site_authority,
            bundle.finalization.resume_authority,
        )
        assert isinstance(capture, OriginalTaskSiteCaptureAuthority)
        assert isinstance(resume, OriginalTaskSiteResumeAuthority)
        assert (
            result.evaluation.status == "success"
            and capture.consumed
            and resume.consumed
        )
        intent_ref = next(
            r
            for r in bundle.capture.state.references
            if r.content_schema == "site-capture-intent/2"
        )
        cap = bundle.capture.reads.parse(
            intent_ref, "site-capture-intent/2", SiteCaptureIntent, guard()
        )
        with pytest.raises(DispatchAlreadyCommitted):
            capture.verify_capture(
                bundle.preparation.spec.configuration, cap.request, intent_ref, guard()
            )
        resume_ref = bundle.finalization.state.resume_intent_ref
        assert resume_ref is not None
        res = bundle.finalization.reads.parse(
            resume_ref, "site-resume-intent/1", SiteResumeIntent, guard()
        )
        with pytest.raises(DispatchAlreadyCommitted):
            resume.verify_resume(
                bundle.preparation.spec.configuration, res.request, resume_ref, guard()
            )
        assert case.native.loader.session.calls == 1
