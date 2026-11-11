"""Full current entry refuses another qualified private source before browser acquire."""

from dataclasses import replace
from pathlib import Path
import os
import traceback
from typing import Any
import pytest
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.bootstrap.map_task_execution_bindings import TaskInitialBinding
from map_task_execution_current_fixtures import current_map_execution_case
from map_navigation_group_cases import SOURCES
from test_map_origin_lineage import alternate_source
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
import map_task_execution_current_fixtures as current_fixtures
from map_task_execution_initialization_fixtures import (
    current_initial_binding as original_factory,
)


def test_current_default_same_public_other_private_source_refused_before_browser_and_no_replay(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacement: list[Any] = []

    def wrong_source(*args: Any, **kwargs: Any) -> TaskInitialBinding:
        selected = original_factory(*args, **kwargs)
        p, handles = args[0], args[3]
        assert len(replacement) == 1
        declaration = selected.declaration.model_copy(
            update={"source_context_receipt_ref": replacement[0]}
        )
        changed = replace(
            selected,
            declaration=declaration,
            declaration_ref=put(p.original.resource.evidence, declaration),
        )
        handles.binding = changed
        return changed

    monkeypatch.setattr(current_fixtures, "current_initial_binding", wrong_source)
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as case:
        replacement.append(alternate_source(case))
        p, bundle = case.p, case.bundle
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            bundle.task.execute(p.plan.intent, p.plan.operation)
        error = caught.value
        output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
        if output:
            with (Path(output) / "private-source-refusal-full-exception.txt").open(
                "w"
            ) as log:
                traceback.print_exception(error, file=log)
        assert isinstance(error.primary, TaskInitializationUnconfirmed)
        assert error.primary.failed_phase == "admission"
        assert isinstance(error.primary.primary, OwnershipConflict)
        assert (
            str(error.primary.primary)
            == "Initialization changed original starting output/task/reset"
        )
        assert error.evaluation is None and error.cleanup_errors == ()
        assert case.native.loader.session.calls == 0
        assert (
            case.handles.backend is not None
            and case.handles.backend.resource.channels == []
        )
        assert case.handles.backend.engines == []
        assert [request.action for request in p.requests] == [
            "snapshot",
            "prepare",
            "restore",
        ]
        assert (
            bundle.finalization.state.reset is not None
            and bundle.finalization.state.reset.status == "safe"
        )
        with pytest.raises(DispatchAlreadyCommitted):
            bundle.task.execute(p.plan.intent, p.plan.operation)
        assert case.handles.backend.resource.channels == []
