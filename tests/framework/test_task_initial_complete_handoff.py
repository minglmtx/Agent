"""Existing complete publication reaches actual initializer; no duplicate capture."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OperationStopped
from site_instance_fixtures import node_path as node_path
from task_initialization_port_fixtures import initialization_case


@pytest.mark.parametrize("fault", ["none", "reference", "body", "selection", "cancel"])
def test_record_complete_reaches_baseline_and_failure_retains_original_browser(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with initialization_case(node_path, monkeypatch) as c:
        initial = c.initialization
        producer = initial.measurements
        assert isinstance(producer, CapturedTaskInitialMeasurements)
        record = producer.record_complete
        read = InitialObservationReader.load_complete
        reads = []
        publications = []

        def traced(self: Any, *args: Any, **kwargs: Any) -> Any:
            result = read(self, *args, **kwargs)
            reads.append(result)
            return result

        def complete(*args: Any, **kwargs: Any) -> Any:
            result = record(*args, **kwargs)
            publications.append(result)
            if fault == "reference":
                return replace(
                    result,
                    reference=result.reference.model_copy(
                        update={"producer": "foreign"}
                    ),
                )
            if fault == "body":
                return replace(
                    result,
                    value=result.value.model_copy(
                        update={"measured_state_sha256": "f" * 64}
                    ),
                )
            if fault == "selection":
                selection = result.inputs.selection.model_copy(
                    update={
                        "browser_spec_ref": result.inputs.selection.browser_spec_ref.model_copy(
                            update={"producer": "foreign"}
                        )
                    }
                )
                return replace(
                    result,
                    inputs=result.inputs.model_copy(update={"selection": selection}),
                )
            if fault == "cancel":
                error = OperationStopped(
                    "CANCELLED", initial.declaration.initial_operation.operation_id
                )
                setattr(error, "initial_checks_reference", result.reference)
                raise error
            return result

        monkeypatch.setattr(InitialObservationReader, "load_complete", traced)
        monkeypatch.setattr(producer, "record_complete", complete)
        if fault == "none":
            result = c.start()
            assert (
                result.actor.initial_observation_ref
                == publications[0].value.observation_ref
            )
            assert initial.state.baseline_inputs is not None
            assert (
                initial.state.baseline_inputs.preparation == publications[0].preparation
            )
        else:
            with pytest.raises(TaskInitializationUnconfirmed) as caught:
                c.start()
            assert caught.value.primary is not None
            assert initial.state.baseline_ref is None
            assert initial.state.result is None
        assert len(reads) == len(publications) == 1
        assert initial._current_initial is None
        assert c.browser.phase == "open"
        with pytest.raises(DispatchAlreadyCommitted):
            c.start()
    assert c.browser.phase == "closed"
