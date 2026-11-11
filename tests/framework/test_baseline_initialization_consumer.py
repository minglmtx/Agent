"""Actual owned initializer and finalizer with explicit synthetic resource rights."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.plans.baseline_read import baseline_input_bodies
from lab_generate_skill.domain.baseline_read import (
    BaselineReadRequest,
    BaselineReadBodies,
)
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.ports.lifecycle import OperationControl
from task_resource_owner_fixtures import owned_task
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("fault", ["none", "cancel"])
def test_owned_initializer_consumes_graph_and_retains_original_failure_close(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        contexts = c.journals.source_reader.contexts
        requests: list[BaselineReadRequest] = []
        original = OperationStopped(
            "CANCELLED", "original-candidate-baseline-input-read"
        )

        def read(
            request: BaselineReadRequest, control: OperationControl
        ) -> BaselineReadBodies:
            requests.append(request)
            if fault == "cancel":
                raise original
            return baseline_input_bodies(
                request, c.p.original.resource.evidence, control
            )

        monkeypatch.setattr(contexts, "load_baseline_inputs", read)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert c.native.loader.session.calls == 1
            assert requests and all(
                req.receipt.scope.task == c.p.plan.intent.binding.task
                for req in requests
            )
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as caught:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            primary = caught.value.primary
            assert primary is not None and getattr(primary, "primary", None) is original
            assert c.native.loader.session.calls == 0 and len(requests) == 1
        browser = r.browser()
        assert browser is not None and browser.phase == "closed"
        reset = c.bundle.finalization.state.reset
        assert reset is not None and reset.status == "safe"
