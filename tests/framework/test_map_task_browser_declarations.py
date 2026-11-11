"""Actual preparation references on explicit synthetic source/model premises."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.map_task_browser_declarations import (
    OriginalMapNavigationBrowserDeclarations,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from task_resource_owner_fixtures import owned_task
from site_instance_fixtures import node_path as node_path


def test_late_default_browser_declarations_use_actual_preparation_and_original_assets(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        original = c.bundle.initialization.factory
        seen: list[bool] = []

        def factory(
            plan: TaskExecutionPlan,
            op: OperationContext,
            control: OperationControl,
        ) -> RecordedTaskInitialization:
            current = original(plan, op, control)
            b = r.browser()
            assert b is not None and b.phase == "new"
            assert c.native.loader.session.calls == 0
            before = len(c.p.requests)
            builder = OriginalMapNavigationBrowserDeclarations(
                r.owner,
                r.model,
                c.p.reset,
                b.spec.configuration,
                current.declaration.actor,
            )
            # No model/site/browser call; only actual current prepared refs and
            # immutable declarations. The original holder still owns its token.
            value = builder(c.bundle.preparation, op, control)
            assert value.spec.token == b.spec.token
            assert value.spec.configuration.spec == b.spec.configuration.spec
            assert (
                value.spec.configuration.initialization
                == b.spec.configuration.initialization
            )
            assert value.spec.slurm == b.spec.slurm
            assert (
                value.initial.prepared_result_ref
                == c.bundle.preparation.state.result_ref
            )
            assert value.initial.source_context_receipt_ref == c.journals.source_ref
            assert value.initial.actor == current.declaration.actor
            assert len(c.p.requests) == before and c.native.loader.session.calls == 0
            with pytest.raises(DispatchAlreadyCommitted):
                builder(c.bundle.preparation, op, control)
            seen.append(True)
            return current

        monkeypatch.setattr(c.bundle.initialization, "factory", factory)
        result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert seen == [True] and result.evaluation.status == "success"
