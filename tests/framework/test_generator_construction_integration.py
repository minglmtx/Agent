"""Actual role evidence feeds existing construction state without digest rebinding."""

import json
from pathlib import Path
from generator_fixtures import fixture, put
from lab_generate_skill.domain.construction import CallPlanned, CallCompleted
from test_construction_state import initial, planned_call, append
from test_run_journal import command
from release_current_fixtures import op


def test_recorded_candidate_matches_existing_call_contract(tmp_path: Path) -> None:
    case = fixture(tmp_path)
    progress = initial()
    planned = planned_call(progress)
    request = case.request.model_copy(
        update={
            "request_id": planned.call.request_id,
            "seed": planned.call.seed,
            "temperature": planned.call.temperature,
        }
    )
    input_ref = put(
        case.evidence, request.model_dump_json().encode(), "generation-input/1", True
    )
    parameters_ref = put(
        case.evidence,
        json.dumps(
            {
                "seed": request.seed,
                "temperature": request.temperature,
                "max_new_tokens": 1024,
            }
        ).encode(),
        "model-parameters/1",
    )
    call = planned.call.model_copy(
        update={"input_ref": input_ref, "parameters_ref": parameters_ref}
    )
    progress = append(progress, CallPlanned(operation=planned.operation, call=call))
    result = case.generator.generate(request, op("generator"))
    completed = append(progress, CallCompleted(operation=command(), response=result))
    assert len(completed.events) == 2 and completed.revision == 1
    assert completed.project().pending_call is None
    assert completed.project().candidates[0].response == result
    assert (
        result.input_sha256 == input_ref.sha256
        and result.parameters_sha256 == parameters_ref.sha256
    )
