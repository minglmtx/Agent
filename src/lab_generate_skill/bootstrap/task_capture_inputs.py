"""Read actual completed phase facts, never predict preparation/initial refs."""

from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.domain.task_capture import TaskCaptureInputs
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl


def initialized_task_capture_inputs(
    preparation: RecordedSiteTaskPreparation,
    initialization: RecordedTaskInitialization,
    control: OperationControl,
) -> TaskCaptureInputs:
    control.checkpoint()
    p, i, measurements = (
        preparation.state,
        initialization.state,
        initialization.measurements,
    )
    if (
        preparation.plan != initialization.plan
        or p.result is None
        or p.result_ref is None
        or i.phase != "initialized"
        or i.result is None
        or i.selection is None
        or i.baseline_inputs is None
        or initialization.declaration.prepared_result_ref != p.result_ref
        or not isinstance(measurements, CapturedTaskInitialMeasurements)
        or measurements.capture is None
        or measurements.capture.intent_ref is None
        or measurements.capture.result_ref is None
    ):
        raise OwnershipConflict(
            "Actual original completed preparation/initialization required"
        )
    return TaskCaptureInputs(
        initialized=i.result,
        initial=i.selection,
        initial_capture_intent_ref=measurements.capture.intent_ref,
        initial_capture_result_ref=measurements.capture.result_ref,
        initial_checks_ref=i.baseline_inputs.initial_ref,
        environment_selection_ref=p.result.environment_selection_ref,
        prepare_request_ref=p.result.publication.selection.request_ref,
    )
