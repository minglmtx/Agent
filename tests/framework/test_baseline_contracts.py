"""Initial-state composition: one observation, fixed scope and declared checks."""

from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.baseline import (
    BaselineInputs,
    BaselineReceipt,
    assemble_baseline,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.preparation import (
    PreparedTask,
    EnvironmentBaseline,
    PreparationReceipt,
)
from lab_generate_skill.domain.state_checks import StateChecks
from retrieval_fixtures import reference
from state_contract_fixtures import baseline_inputs, op, checks


def test_baseline_roundtrip_and_repeat_keep_same_initial_facts() -> None:
    inputs = baseline_inputs()
    operation = op("baseline")
    result = assemble_baseline(inputs, operation)
    assert result.status == "ready" and result.observation_ref == inputs.observation_ref
    assert result.measured_state_sha256 == inputs.initial.measured_state_sha256
    assert (
        result.spec_ref == inputs.spec_ref
        and result.equivalence_scope == inputs.spec.equivalence_checks
    )
    assert (
        assemble_baseline(
            BaselineInputs.model_validate_json(inputs.model_dump_json()), operation
        )
        == result
    )
    assert BaselineReceipt.model_validate_json(result.model_dump_json()) == result
    assert "initial_observation" not in inputs.prepared.model_dump()


@pytest.mark.parametrize("stage", ["environment", "preparation", "initial"])
@pytest.mark.parametrize("status", ["fail", "unknown", "missing"])
def test_nonpassing_phase_never_produces_ready(stage: str, status: str) -> None:
    inputs = baseline_inputs()
    fact = getattr(inputs, stage)
    observed = (
        ()
        if status == "missing"
        else (fact.checks.checks[0].model_copy(update={"status": status}),)
    )
    changed = fact.model_copy(
        update={"checks": StateChecks(required=fact.checks.required, checks=observed)}
    )
    result = assemble_baseline(
        inputs.model_copy(update={stage: changed}), op("baseline")
    )
    assert result.status == ("rejected" if status == "fail" else "unknown")


@pytest.mark.parametrize("state", ["loading", "error", "unavailable", "action_error"])
def test_observation_failure_stays_unknown_even_with_passing_checks(state: str) -> None:
    inputs = baseline_inputs()
    change: dict[str, object] = {
        "state": state,
        "error_code": "NOT_READY" if state in ("error", "unavailable") else None,
    }
    if state == "action_error":
        change = {"last_action_error": "Failed action"}
    inputs = inputs.model_copy(
        update={"observation": inputs.observation.model_copy(update=change)}
    )
    assert assemble_baseline(inputs, op("baseline")).status == "unknown"


@pytest.mark.parametrize(
    "fault",
    [
        "task",
        "context",
        "attempt",
        "owner",
        "spec",
        "environment_link",
        "preparation_link",
        "prepared_link",
        "observation_link",
        "recovery",
        "binding",
        "public_task",
        "sequence",
        "coverage",
        "operation_reuse",
    ],
)
def test_mixed_or_reduced_initial_facts_rejected(fault: str) -> None:
    inputs = baseline_inputs()
    if fault in ("task", "context", "attempt", "owner"):
        scope = inputs.initial.scope
        updates = {
            "task": scope.task.model_copy(update={"task_id": "other"}),
            "context_id": "other",
            "attempt_id": "other",
            "owner": scope.owner.model_copy(update={"worker_id": "other"}),
        }
        field = {"context": "context_id", "attempt": "attempt_id"}.get(fault, fault)
        inputs = inputs.model_copy(
            update={
                "initial": inputs.initial.model_copy(
                    update={"scope": scope.model_copy(update={field: updates[field]})}
                )
            }
        )
    elif fault == "spec":
        inputs = inputs.model_copy(
            update={"spec_ref": reference({}, "initial-state-spec/1")}
        )
    elif fault == "environment_link":
        inputs = inputs.model_copy(
            update={"environment_ref": reference({}, "environment-baseline/1")}
        )
    elif fault == "preparation_link":
        inputs = inputs.model_copy(
            update={"preparation_ref": reference({}, "preparation-receipt/1")}
        )
    elif fault == "prepared_link":
        inputs = inputs.model_copy(
            update={"prepared_ref": reference({}, "prepared-task/1")}
        )
    elif fault == "observation_link":
        inputs = inputs.model_copy(
            update={"observation_ref": reference({}, "observation/1", "public")}
        )
    elif fault == "recovery":
        inputs = inputs.model_copy(
            update={
                "prepared": inputs.prepared.model_copy(
                    update={"recovery_ref": reference({}, "recovery-plan/1")}
                )
            }
        )
    elif fault == "binding":
        inputs = inputs.model_copy(
            update={
                "binding": inputs.binding.model_copy(
                    update={"private_spec_ref": reference({"other": True})}
                )
            }
        )
    elif fault == "public_task":
        inputs = inputs.model_copy(
            update={
                "public_task": inputs.public_task.model_copy(update={"goal": "other"})
            }
        )
    elif fault == "sequence":
        inputs = inputs.model_copy(
            update={
                "observation": inputs.observation.model_copy(update={"sequence": 1})
            }
        )
    elif fault == "coverage":
        inputs = inputs.model_copy(
            update={
                "initial": inputs.initial.model_copy(
                    update={"checks": checks(("different",))}
                )
            }
        )
    else:
        with pytest.raises(OwnershipConflict):
            assemble_baseline(inputs, inputs.initial.operation)
        return
    with pytest.raises((OwnershipConflict, ValidationError)):
        assemble_baseline(inputs, op("baseline"))


@pytest.mark.parametrize(
    "field", ["initial_observation", "private_checks_ref", "public_task"]
)
def test_prepared_task_cannot_supply_second_observation_or_leak_checks(
    field: str,
) -> None:
    inputs = baseline_inputs()
    value: object = "another observation"
    if field == "private_checks_ref":
        value = reference({}, visibility="public")
    if field == "public_task":
        value = inputs.public_task.model_copy(
            update={
                "identity": inputs.public_task.identity.model_copy(
                    update={"task_id": "other"}
                )
            }
        )
    with pytest.raises(ValidationError):
        PreparedTask.model_validate(inputs.prepared.model_copy(update={field: value}))


@pytest.mark.parametrize(
    "fault", ["wrong_allocation", "different_owner", "wrong_recovery", "cleanup"]
)
def test_preparation_uses_owned_allocation_and_registered_recovery(fault: str) -> None:
    inputs = baseline_inputs()
    if fault == "wrong_allocation":
        with pytest.raises(ValidationError):
            EnvironmentBaseline.model_validate(
                inputs.environment.model_copy(
                    update={
                        "operation": inputs.environment.operation.model_copy(
                            update={"allocation_id": "other"}
                        )
                    }
                )
            )
    elif fault == "different_owner":
        with pytest.raises(ValidationError):
            EnvironmentBaseline.model_validate(
                inputs.environment.model_copy(
                    update={
                        "allocation": inputs.environment.allocation.model_copy(
                            update={
                                "owner": inputs.environment.scope.owner.model_copy(
                                    update={"worker_id": "other"}
                                )
                            }
                        )
                    }
                )
            )
    elif fault == "wrong_recovery":
        with pytest.raises(ValidationError):
            PreparationReceipt.model_validate(
                inputs.preparation.model_copy(
                    update={
                        "operation": inputs.preparation.operation.model_copy(
                            update={"recovery_ref": None}
                        )
                    }
                )
            )
    else:
        with pytest.raises(OwnershipConflict):
            assemble_baseline(inputs, op("baseline", cleanup=True))


@pytest.mark.parametrize("bad", [None, {}, [], True])
def test_bad_baseline_root_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        assemble_baseline(cast(BaselineInputs, bad), op("baseline"))


def test_site_baseline_uses_batch_lease_not_attempt_resource() -> None:
    inputs = baseline_inputs()
    token = inputs.environment.allocation.model_copy(
        update={"scope": "attempt", "attempt_id": "attempt"}
    )
    with pytest.raises(ValidationError, match="batch site lease"):
        EnvironmentBaseline.model_validate(
            inputs.environment.model_copy(update={"allocation": token})
        )
