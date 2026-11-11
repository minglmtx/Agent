"""Actual retained producer inputs through original pure initialization policy."""

import os
from typing import Any
import pytest
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.policies.task_initialization import (
    require_original_initialization,
)
from initialization_binding_retained_fixtures import retained_inputs


@pytest.fixture(scope="module", params=["Admin", "Map"])
def original(request: pytest.FixtureRequest) -> tuple[str, dict[str, Any]]:
    assert os.environ.get("SLURM_JOB_ID")
    return request.param, retained_inputs(request.param)


def test_actual_wrapped_and_direct_inputs_preserve_original_private_completion_binding(
    original: tuple[str, dict[str, Any]],
) -> None:
    site, inputs = original
    same = (
        inputs["prepared_plan"].private_input_ref
        == inputs["prepared"].private_checks_ref
    )
    assert same == (site == "Map")
    require_original_initialization(**inputs)


@pytest.mark.parametrize(
    "fault",
    [
        "native-bytes",
        "native-size",
        "native-digest",
        "native-binding",
        "native-action",
        "completion",
        "private-spec",
    ],
)
def test_actual_inputs_cannot_change_frozen_wire_or_task_private_evaluation_joins(
    original: tuple[str, dict[str, Any]], fault: str
) -> None:
    _, old = original
    inputs = old.copy()
    if fault == "native-bytes":
        inputs["request"] = old["request"].model_copy(
            update={"private_input": old["request"].private_input + " "}
        )
    elif fault in ("native-size", "native-digest"):
        ref = old["prepared_plan"].private_input_ref
        ref = ref.model_copy(
            update=(
                {"size_bytes": ref.size_bytes + 1}
                if fault == "native-size"
                else {"sha256": "f" * 64}
            )
        )
        inputs["prepared_plan"] = old["prepared_plan"].model_copy(
            update={"private_input_ref": ref}
        )
    elif fault == "native-binding":
        inputs["request"] = old["request"].model_copy(
            update={
                "binding_ref": old["request"].binding_ref.model_copy(
                    update={"producer": "foreign"}
                )
            }
        )
    elif fault == "native-action":
        inputs["request"] = old["request"].model_copy(update={"action": "inspect"})
    elif fault == "completion":
        evaluation = old["plan"].evaluation.model_copy(
            update={
                "completion_spec_ref": old[
                    "plan"
                ].evaluation.completion_spec_ref.model_copy(
                    update={"producer": "foreign"}
                )
            }
        )
        inputs["plan"] = old["plan"].model_copy(update={"evaluation": evaluation})
    else:
        inputs["prepared"] = old["prepared"].model_copy(
            update={
                "private_checks_ref": old["prepared"].private_checks_ref.model_copy(
                    update={"producer": "foreign"}
                )
            }
        )
    expected = (
        EvidenceIntegrityError
        if fault in ("native-bytes", "native-size", "native-digest")
        else OwnershipConflict
    )
    with pytest.raises(expected):
        require_original_initialization(**inputs)
