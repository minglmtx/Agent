"""All8 on current execute_task/default/Actor binding, original review and restore."""

import os
from pathlib import Path
import shutil
import traceback
import pytest
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.adapters.sites.task_site_capture_authority import (
    OriginalTaskSiteCaptureAuthority,
)
from map_navigation_group_cases import SOURCES
from map_navigation_evaluation_fixtures import closed_review
from map_task_execution_current_fixtures import current_map_execution_case
from map_task_execution_review_fixtures import current_map_review_facts
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("source_id", SOURCES)
def test_complete_map_group_uses_production_default_current_journals_actor_and_closed_review(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
) -> None:
    with current_map_execution_case(node_path, monkeypatch, source_id) as case:
        p, bundle = case.p, case.bundle
        try:
            result = bundle.task.execute(p.plan.intent, p.plan.operation)
        except TaskExecutionUnconfirmed as error:
            if error.primary is not None:
                traceback.print_exception(error.primary)
            for failure in error.cleanup_errors:
                traceback.print_exception(failure)
            destination = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
            if destination:
                saved = Path(destination) / ("failed-current-map-" + source_id)
                shutil.copytree(p.original.workspace, saved, dirs_exist_ok=True)
            raise
        assert result.evaluation.status == "success"
        assert isinstance(
            bundle.capture.site_authority, OriginalTaskSiteCaptureAuthority
        )
        assert bundle.capture.site_authority.consumed
        assert case.task_source._native is bundle.native_authority
        assert (
            result.generations
            == result.interactions
            == case.native.loader.session.calls
            == len(case.handles.completed)
            == 1
        )
        assert bundle.initialization.original().state.result is not None
        assert (
            case.handles.backend is not None
            and case.handles.backend.calls.count("actual_action") == 1
        )
        attempt = case.journals.runs.read(p.plan.read_operation).project()[1][0]
        assert attempt.stage == "sealed"
        assert [e.stage for e in attempt.events] == [
            "planned",
            "acquiring",
            "preparing",
            "starting",
            "baseline_verified",
            "executing",
            "captured",
            "evaluated",
            "closing",
            "restoring",
            "sealed",
        ]
        facts = current_map_review_facts(case, result)
        for request in (
            bundle.preparation.state.snapshot_request,
            bundle.preparation.state.prepare_request,
            bundle.finalization.state.restore_request,
        ):
            assert request is not None
            with pytest.raises(OwnershipConflict, match="not awaiting"):
                bundle.native_authority.verify_task(
                    p.original.resource.spec.configuration,
                    request,
                    p.original.resource.controls.bind(request.operation),
                )
        with pytest.raises(DispatchAlreadyCommitted):
            bundle.task.execute(p.plan.intent, p.plan.operation)
        assert case.native.loader.session.calls == 1
        original = p.original
    try:
        closed_review(original, facts)
    except BaseException:
        destination = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
        if destination:
            saved = Path(destination) / ("failed-closed-map-" + source_id)
            shutil.copytree(original.workspace, saved, dirs_exist_ok=True)
        raise
