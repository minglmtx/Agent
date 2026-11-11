"""Source projection/facts/cleanup gates, deterministic replay and bad inputs."""

from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.baseline import assemble_baseline
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
    assemble_public_context,
)
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.domain.state_checks import StateChecks
from context_contract_fixtures import source_inputs
from retrieval_fixtures import reference
from test_run_journal import command


def test_freeze_roundtrip_repeat_and_private_separation() -> None:
    inputs = source_inputs()
    operation = command("freeze")
    frozen = assemble_public_context(inputs, operation)
    assert (
        frozen.baseline_ref == inputs.baseline_ref
        and frozen.reset_ref == inputs.reset_ref
    )
    assert frozen.scope == inputs.baseline.scope
    assert (
        assemble_public_context(
            PublicContextInputs.model_validate_json(inputs.model_dump_json()), operation
        )
        == frozen
    )
    assert PublicContextReceipt.model_validate_json(frozen.model_dump_json()) == frozen
    assert set(inputs.context.model_dump()) == {
        "schema_version",
        "context_id",
        "task",
        "initial_observation_ref",
    }
    assert frozen.operation.attempt_id is None


@pytest.mark.parametrize("stage", ["baseline", "reset"])
@pytest.mark.parametrize("status", ["fail", "unknown", "missing"])
def test_ineligible_actual_source_is_not_frozen(stage: str, status: str) -> None:
    inputs = source_inputs()
    fact = (
        inputs.baseline_inputs.initial
        if stage == "baseline"
        else inputs.reset_inputs.health
    )
    changed_checks = (
        ()
        if status == "missing"
        else tuple(c.model_copy(update={"status": status}) for c in fact.checks.checks)
    )
    changed = fact.model_copy(
        update={
            "checks": StateChecks(required=fact.checks.required, checks=changed_checks)
        }
    )
    if stage == "baseline":
        initial = inputs.baseline_inputs.model_copy(update={"initial": changed})
        inputs = inputs.model_copy(
            update={
                "baseline_inputs": initial,
                "baseline": assemble_baseline(initial, inputs.baseline.operation),
            }
        )
    else:
        restoration = inputs.reset_inputs.model_copy(update={"health": changed})
        inputs = inputs.model_copy(
            update={
                "reset_inputs": restoration,
                "reset": assemble_reset(restoration, inputs.reset.operation),
            }
        )
    with pytest.raises(InvalidTransition, match="ready and safely reset"):
        assemble_public_context(inputs, command("freeze"))


@pytest.mark.parametrize("field", ["context_id", "task", "initial_observation_ref"])
def test_public_projection_cannot_be_rewritten(field: str) -> None:
    inputs = source_inputs()
    updates: dict[str, object] = {
        "context_id": "other",
        "task": inputs.context.task.model_copy(update={"goal": "other"}),
        "initial_observation_ref": reference({}, "observation/1", "public"),
    }
    with pytest.raises(OwnershipConflict, match="projection"):
        assemble_public_context(
            inputs.model_copy(
                update={
                    "context": inputs.context.model_copy(update={field: updates[field]})
                }
            ),
            command("freeze"),
        )


@pytest.mark.parametrize(
    "fault",
    [
        "baseline_status",
        "reset_status",
        "scope",
        "spec",
        "task_recovery",
        "site_recovery",
    ],
)
def test_forged_summary_or_unrelated_reset_rejected(fault: str) -> None:
    inputs = source_inputs()
    if fault == "baseline_status":
        inputs = inputs.model_copy(
            update={
                "baseline": inputs.baseline.model_copy(update={"status": "unknown"})
            }
        )
    elif fault == "reset_status":
        inputs = inputs.model_copy(
            update={"reset": inputs.reset.model_copy(update={"status": "quarantined"})}
        )
    elif fault in ("scope", "spec"):
        # Even structurally valid altered summary fields cannot stand in for facts.
        change: dict[str, object] = (
            {"scope": inputs.reset.scope.model_copy(update={"context_id": "other"})}
            if fault == "scope"
            else {"spec_ref": reference({}, "initial-state-spec/1")}
        )
        if fault == "scope":
            inputs = inputs.model_copy(
                update={"reset": inputs.reset.model_copy(update=change)}
            )
        else:
            inputs = inputs.model_copy(
                update={"baseline": inputs.baseline.model_copy(update=change)}
            )
    else:
        initial = inputs.baseline_inputs
        replacement = reference({"other": True}, "recovery-plan/1")
        if fault == "task_recovery":
            prep = initial.preparation.model_copy(
                update={
                    "recovery_ref": replacement,
                    "operation": initial.preparation.operation.model_copy(
                        update={"recovery_ref": replacement}
                    ),
                }
            )
            initial = initial.model_copy(
                update={
                    "preparation": prep,
                    "prepared": initial.prepared.model_copy(
                        update={"recovery_ref": replacement}
                    ),
                }
            )
        else:
            initial = initial.model_copy(
                update={
                    "environment": initial.environment.model_copy(
                        update={
                            "allocation": initial.environment.allocation.model_copy(
                                update={"recovery_ref": replacement}
                            )
                        }
                    )
                }
            )
        inputs = inputs.model_copy(update={"baseline_inputs": initial})
    with pytest.raises(OwnershipConflict):
        assemble_public_context(inputs, command("freeze"))


@pytest.mark.parametrize(
    "fault",
    [
        "run",
        "owner",
        "attempt",
        "cleanup",
        "allocation",
        "recovery",
        "reuse",
        "close_reuse",
    ],
)
def test_freeze_operation_cannot_borrow_other_scope_or_stage(fault: str) -> None:
    inputs = source_inputs()
    updates: dict[str, object] = {
        "run": {"run_id": "other"},
        "owner": {"owner_id": "other"},
        "attempt": {"attempt_id": "attempt"},
        "cleanup": {"mode": "cleanup", "parent_operation_id": "parent"},
        "allocation": {"allocation_id": "site"},
        "recovery": {"recovery_ref": reference({}, "recovery-plan/1")},
        "reuse": {"operation_id": inputs.baseline.operation.operation_id},
        "close_reuse": {"operation_id": inputs.reset_inputs.closures[0].operation_id},
    }
    operation = command("freeze").model_copy(
        update=cast(dict[str, object], updates[fault])
    )
    with pytest.raises(OwnershipConflict):
        assemble_public_context(inputs, operation)


@pytest.mark.parametrize("field", ["context_ref", "baseline_ref", "reset_ref"])
@pytest.mark.parametrize("fault", ["visibility", "schema"])
def test_receipt_reference_contracts(field: str, fault: str) -> None:
    inputs = source_inputs()
    ref = getattr(inputs, field)
    update = (
        {"visibility": "teacher"}
        if fault == "visibility"
        else {"content_schema": "obsolete/1"}
    )
    with pytest.raises(ValidationError):
        assemble_public_context(
            inputs.model_copy(update={field: ref.model_copy(update=update)}),
            command("freeze"),
        )


@pytest.mark.parametrize("bad", [None, {}, [], True, "context", 1])
def test_invalid_root_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        assemble_public_context(cast(PublicContextInputs, bad), command("freeze"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("equivalence_scope", ()),
        ("equivalence_scope", ("x", "x")),
        ("equivalence_scope", ["x"]),
        ("schema_version", "public-context-receipt/0"),
        ("unexpected", True),
    ],
)
def test_receipt_revalidates_illegal_fields(field: str, value: object) -> None:
    receipt = assemble_public_context(source_inputs(), command("freeze"))
    with pytest.raises(ValidationError):
        PublicContextReceipt.model_validate({**receipt.model_dump(), field: value})
