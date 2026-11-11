"""Initialization declaration boundaries; no native/Actor/source execution."""

from typing import Any
import pytest
from lab_generate_skill.domain.task_initialization import (
    TaskActorInitialization,
    TaskInitializationPlan,
)
from lab_generate_skill.domain.optional_policies import InactivePolicy
from state_contract_fixtures import scope, op, allocation
from test_core_contracts import reference


def declaration() -> TaskInitializationPlan:
    browser = allocation("browser")
    start = op(
        "browser-initial",
        allocation=browser.allocation_id,
        recovery=browser.recovery_ref,
    )
    actor = TaskActorInitialization(
        candidate_id="candidate-zero",
        revision_round=0,
        context_configuration_ref=reference("private", "actor-context-configuration/1"),
        memory=InactivePolicy(
            status="disabled", reason="explicit contract fixture; no online memory"
        ),
        model_allocation=allocation("actor", attempt=False),
        parameters_refs=(reference("private", "model-parameters/1"),),
        generation_seconds=30,
        interaction_seconds=30,
        cleanup_seconds=30,
    )
    return TaskInitializationPlan(
        scope=scope(),
        prepared_result_ref=reference("private", "site-task-prepared/2"),
        source_context_receipt_ref=reference("private", "public-context-receipt/1"),
        browser_spec_ref=reference("private", "browser-resource-spec/4"),
        browser_acquisition=start,
        capture_operation=start.model_copy(update={"operation_id": "initial-capture"}),
        initial_operation=op("initial-checks"),
        baseline_operation=op("initial-baseline"),
        comparison_operation=op("initial-comparison"),
        equivalence_operation=op("initial-equivalence"),
        actor=actor,
    )


def test_exact_initialization_declaration_roundtrips_without_effects() -> None:
    value = declaration()
    assert TaskInitializationPlan.model_validate_json(value.model_dump_json()) == value
    assert (
        len(
            {
                x.operation_id
                for x in (
                    value.browser_acquisition,
                    value.capture_operation,
                    value.initial_operation,
                    value.baseline_operation,
                    value.comparison_operation,
                    value.equivalence_operation,
                )
            }
        )
        == 6
    )


@pytest.mark.parametrize("invalid", [None, "", [], {}, True, 1])
def test_empty_wrong_type_initialization_declaration_is_rejected(invalid: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        TaskInitializationPlan.model_validate(invalid)


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate-operation",
        "foreign-operation",
        "dev",
        "capture-recovery",
        "public-source",
        "empty-reference",
        "wrong-mime",
        "model-owner",
        "model-role",
        "missing-parameters",
        "wrong-parameters-type",
        "extreme-parameters",
        "public-context-config",
    ],
)
def test_original_role_scope_stage_and_complete_references_are_required(
    fault: str,
) -> None:
    value = declaration()
    changes: dict[str, Any] = {}
    if fault == "duplicate-operation":
        changes["capture_operation"] = value.browser_acquisition
    elif fault == "foreign-operation":
        changes["baseline_operation"] = value.baseline_operation.model_copy(
            update={"attempt_id": "foreign"}
        )
    elif fault == "dev":
        changes["scope"] = value.scope.model_copy(
            update={"task": value.scope.task.model_copy(update={"split": "dev"})}
        )
    elif fault == "capture-recovery":
        changes["capture_operation"] = value.capture_operation.model_copy(
            update={"recovery_ref": reference()}
        )
    elif fault in ("public-source", "empty-reference", "wrong-mime"):
        changes["source_context_receipt_ref"] = (
            value.source_context_receipt_ref.model_copy(
                update=(
                    {"visibility": "public"}
                    if fault == "public-source"
                    else (
                        {"size_bytes": 0}
                        if fault == "empty-reference"
                        else {"media_type": "text/plain"}
                    )
                )
            )
        )
    else:
        actor: dict[str, Any] = {}
        if fault == "model-owner":
            actor["model_allocation"] = value.actor.model_allocation.model_copy(
                update={
                    "owner": value.scope.owner.model_copy(
                        update={"owner_id": "foreign"}
                    )
                }
            )
        elif fault == "model-role":
            actor["model_allocation"] = value.actor.model_allocation.model_copy(
                update={"resource_kind": "teacher"}
            )
        elif fault == "missing-parameters":
            actor["parameters_refs"] = ()
        elif fault == "wrong-parameters-type":
            actor["parameters_refs"] = list(value.actor.parameters_refs)
        elif fault == "extreme-parameters":
            actor["parameters_refs"] = value.actor.parameters_refs * 10001
        else:
            actor["context_configuration_ref"] = (
                value.actor.context_configuration_ref.model_copy(
                    update={"visibility": "public"}
                )
            )
        changes["actor"] = value.actor.model_copy(update=actor)
    with pytest.raises(ValueError):
        TaskInitializationPlan.model_validate(value.model_copy(update=changes))
