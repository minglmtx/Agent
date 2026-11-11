"""Normal reset keeps all original resources and unsuccessful cleanup facts."""

from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import CleanupFailure
from lab_generate_skill.domain.reset import (
    ResetPlan,
    ResetInputs,
    ResetReceipt,
    assemble_reset,
)
from lab_generate_skill.domain.state_checks import StateChecks
from retrieval_fixtures import reference
from state_contract_fixtures import reset_inputs, op, checks, allocation


def test_reset_without_prepared_task_roundtrip_and_repeat() -> None:
    inputs = reset_inputs()
    operation = op("reset-summary", cleanup=True)
    result = assemble_reset(inputs, operation)
    assert result.status == "safe"
    assert result.closure_refs == inputs.closure_refs
    assert (
        "prepared" not in inputs.model_dump() and "baseline" not in inputs.model_dump()
    )
    assert (
        assemble_reset(
            ResetInputs.model_validate_json(inputs.model_dump_json()), operation
        )
        == result
    )
    assert ResetReceipt.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("stage", ["task", "environment", "health"])
@pytest.mark.parametrize("status", ["fail", "unknown", "missing"])
def test_each_failure_quarantines_even_when_other_components_pass(
    stage: str, status: str
) -> None:
    inputs = reset_inputs()
    fact = getattr(inputs, stage)
    observed = (
        ()
        if status == "missing"
        else (
            fact.checks.checks[0].model_copy(update={"status": status}),
            *fact.checks.checks[1:],
        )
    )
    changed = fact.model_copy(
        update={"checks": StateChecks(required=fact.checks.required, checks=observed)}
    )
    inputs = inputs.model_copy(update={stage: changed})
    assert (
        assemble_reset(inputs, op("reset-summary", cleanup=True)).status
        == "quarantined"
    )


@pytest.mark.parametrize("status", ["failed", "unconfirmed"])
def test_failed_closure_is_never_cured_by_successful_reset(status: str) -> None:
    inputs = reset_inputs()
    errors = (
        (CleanupFailure(component_id="browser", reason_code="CLOSE_FAILED"),)
        if status == "failed"
        else ()
    )
    changed = inputs.closures[0].model_copy(
        update={"status": status, "cleanup_errors": errors}
    )
    inputs = inputs.model_copy(update={"closures": (changed, *inputs.closures[1:])})
    assert (
        assemble_reset(inputs, op("reset-summary", cleanup=True)).status
        == "quarantined"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "scope",
        "parent",
        "missing_closure",
        "reversed_closures",
        "wrong_resource",
        "extra_closure",
        "refs",
        "task_link",
        "environment_link",
        "recovery",
        "recovery_owner",
        "recovery_attempt",
        "recovery_coverage",
        "checks_coverage",
        "spec_task",
        "operation_reuse",
    ],
)
def test_inconsistent_or_reduced_reset_facts_rejected(fault: str) -> None:
    inputs = reset_inputs()
    if fault == "scope":
        inputs = inputs.model_copy(
            update={
                "health": inputs.health.model_copy(
                    update={
                        "scope": inputs.health.scope.model_copy(
                            update={"context_id": "other"}
                        )
                    }
                )
            }
        )
    elif fault == "parent":
        inputs = inputs.model_copy(
            update={
                "health": inputs.health.model_copy(
                    update={
                        "operation": inputs.health.operation.model_copy(
                            update={"parent_operation_id": "other"}
                        )
                    }
                )
            }
        )
    elif fault == "missing_closure":
        inputs = inputs.model_copy(update={"closures": inputs.closures[:1]})
    elif fault == "reversed_closures":
        inputs = inputs.model_copy(
            update={"closures": tuple(reversed(inputs.closures))}
        )
    elif fault == "wrong_resource":
        inputs = inputs.model_copy(
            update={
                "closures": (
                    inputs.closures[0].model_copy(
                        update={
                            "token": inputs.closures[0].token.model_copy(
                                update={"expected_resource_id": "other"}
                            )
                        }
                    ),
                    *inputs.closures[1:],
                )
            }
        )
    elif fault == "extra_closure":
        inputs = inputs.model_copy(
            update={"closures": inputs.closures + inputs.closures[:1]}
        )
    elif fault == "refs":
        inputs = inputs.model_copy(
            update={"closure_refs": tuple(reversed(inputs.closure_refs))}
        )
    elif fault == "task_link":
        inputs = inputs.model_copy(update={"task_ref": reference({}, "task-reset/1")})
    elif fault == "environment_link":
        inputs = inputs.model_copy(
            update={"environment_ref": reference({}, "environment-reset/1")}
        )
    elif fault == "recovery":
        inputs = inputs.model_copy(
            update={
                "plan": inputs.plan.model_copy(
                    update={"task_recovery_ref": reference({}, "recovery-plan/1")}
                )
            }
        )
    elif fault == "recovery_owner":
        inputs = inputs.model_copy(
            update={
                "task_recovery": inputs.task_recovery.model_copy(
                    update={
                        "owner": inputs.task_recovery.owner.model_copy(
                            update={"worker_id": "other"}
                        )
                    }
                )
            }
        )
    elif fault == "recovery_attempt":
        inputs = inputs.model_copy(
            update={
                "task_recovery": inputs.task_recovery.model_copy(
                    update={"attempt_id": None}
                )
            }
        )
    elif fault == "recovery_coverage":
        inputs = inputs.model_copy(
            update={
                "task_recovery": inputs.task_recovery.model_copy(
                    update={"state_coverage": ("database",)}
                )
            }
        )
    elif fault == "checks_coverage":
        inputs = inputs.model_copy(
            update={
                "task": inputs.task.model_copy(update={"checks": checks(("database",))})
            }
        )
    elif fault == "spec_task":
        inputs = inputs.model_copy(
            update={
                "spec": inputs.spec.model_copy(
                    update={
                        "task": inputs.spec.task.model_copy(update={"task_id": "other"})
                    }
                )
            }
        )
    else:
        with pytest.raises(OwnershipConflict):
            assemble_reset(inputs, inputs.task.operation)
        return
    with pytest.raises((OwnershipConflict, ValidationError)):
        assemble_reset(inputs, op("reset-summary", cleanup=True))


@pytest.mark.parametrize(
    "fault", ["empty", "duplicate", "alias", "batch", "owner", "attempt"]
)
def test_plan_cannot_close_other_or_duplicate_resources(fault: str) -> None:
    plan = reset_inputs().plan
    tokens = plan.attempt_allocations
    if fault == "empty":
        tokens = ()
    elif fault == "duplicate":
        tokens = (tokens[0], tokens[0])
    elif fault == "alias":
        tokens = (tokens[0], tokens[0].model_copy(update={"allocation_id": "alias"}))
    elif fault == "batch":
        tokens = (allocation("site", attempt=False),)
    elif fault == "owner":
        tokens = (
            tokens[0].model_copy(
                update={
                    "owner": tokens[0].owner.model_copy(update={"worker_id": "other"})
                }
            ),
        )
    else:
        tokens = (tokens[0].model_copy(update={"attempt_id": "other"}),)
    with pytest.raises(ValidationError):
        ResetPlan.model_validate(
            plan.model_copy(update={"attempt_allocations": tokens})
        )


def test_cleanup_summary_cannot_be_an_execution_command() -> None:
    with pytest.raises(OwnershipConflict):
        assemble_reset(reset_inputs(), op("summary"))


@pytest.mark.parametrize("bad", [None, {}, [], True])
def test_bad_reset_root_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        assemble_reset(cast(ResetInputs, bad), op("summary", cleanup=True))
