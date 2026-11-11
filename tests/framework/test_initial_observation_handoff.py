"""Actual owned initializer/context authority, with original fixture resource premises."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.bootstrap.owned_preparation_records import (
    owned_preparation_records,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.preparation_read import (
    PreparationReadRequest,
    PreparationReadBodies,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_records import PreparationReceiptReads
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task


@pytest.mark.parametrize("fault", ["none", "scope", "revoked", "cancel"])
def test_real_owned_baseline_consumes_active_initial_bodies_and_keeps_live_gates(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):

        class LocalInputs:
            def load_preparation_inputs(
                self, request: PreparationReadRequest, control: OperationControl
            ) -> PreparationReadBodies | None:
                control.checkpoint()
                return None  # Original local full graph; no synthetic ready input.

        c.bundle.preparation.records = owned_preparation_records(
            c.bundle.preparation.records, LocalInputs()
        )
        assert isinstance(c.bundle.preparation.records, PreparationReceiptReads)
        observed: list[RecordedTaskInitialization] = []
        original_read = InitialObservationReader.load
        original_handoff = RecordedTaskInitialization.current_initial_observation
        original_require = r.require

        def read(self: InitialObservationReader, *args: Any, **kwargs: Any) -> Any:
            if observed and observed[-1]._current_initial is not None:
                pytest.fail(
                    "Baseline authority reread an already verified initial graph"
                )
            return original_read(self, *args, **kwargs)

        def handoff(
            self: RecordedTaskInitialization, operation: Any, control: OperationControl
        ) -> Any:
            observed.append(self)
            if fault == "scope":
                operation = operation.model_copy(update={"operation_id": "foreign"})
            if fault == "cancel":
                raise OperationStopped("CANCELLED", operation.operation_id)
            return original_handoff(self, operation, control)

        def require(operation: Any, control: OperationControl, **kwargs: Any) -> Any:
            if fault == "revoked" and r.browser() is not None:
                initial = c.bundle.initialization.original()
                if initial._current_initial is not None:
                    raise PermissionError("Current baseline resource rights revoked")
            return original_require(operation, control, **kwargs)

        monkeypatch.setattr(InitialObservationReader, "load", read)
        monkeypatch.setattr(
            RecordedTaskInitialization, "current_initial_observation", handoff
        )
        monkeypatch.setattr(r, "require", require)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert c.native.loader.session.calls == 1
            assert observed and all(x is observed[0] for x in observed)
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as caught:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            primary = caught.value.primary
            assert primary is not None
            expected = {
                "scope": OwnershipConflict,
                "revoked": PermissionError,
                "cancel": OperationStopped,
            }[fault]
            assert isinstance(getattr(primary, "primary", None), expected)
            assert c.native.loader.session.calls == 0
        initial = c.bundle.initialization.original()
        assert initial._current_initial is None
        assert (
            original_handoff(
                initial,
                initial.declaration.baseline_operation,
                c.p.original.resource.controls.bind(
                    initial.declaration.baseline_operation
                ),
            )
            is None
        )
        browser = r.browser()
        assert browser is not None and browser.phase == "closed"
