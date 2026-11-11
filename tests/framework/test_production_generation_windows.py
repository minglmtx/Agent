"""Exact selected Map/Admin budget producers, including old canonical input compatibility."""

import json
from pathlib import Path
from typing import Any
import pytest
from production_task_plan import MapProductionBudgets
from admin_production_task_plan import AdminProductionBudgets
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from test_task_initialization_contracts import declaration

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


@pytest.mark.parametrize(
    "site,consumer", [("map", MapProductionBudgets), ("admin", AdminProductionBudgets)]
)
def test_selected_production_round_and_legacy_canonical_input(
    site: str, consumer: Any
) -> None:
    package = (
        "framework-map-navigation42-production-20261102-v1"
        if site == "map"
        else "framework-admin-navigation-production-20261102-v1"
    )
    root = W / "experiments" / package
    raw = json.loads(
        (
            root / "runtime-actor-dispatch-windows-candidate/entry-budgets.json"
        ).read_text()
    )
    budget = consumer.model_validate(raw)
    assert budget.generation_budgets.preparation_seconds == 900
    assert (
        budget.generation_budgets.execution_seconds == budget.generation_seconds == 600
    )
    assert (
        budget.generation_budgets.transaction_seconds
        + budget.interaction_seconds
        + 5 * budget.actor_rpc_cleanup_seconds
        <= budget.stage_budgets.actor_seconds
    )
    assert budget.model_dump(mode="json") == raw
    actor = TaskActorInitialization.model_validate(
        declaration().actor.model_copy(
            update={
                "generation_seconds": budget.generation_seconds,
                "generation_budgets": budget.generation_budgets,
            }
        )
    )
    assert actor.generation_budgets == budget.generation_budgets
    old = json.loads(
        (
            root / "runtime-actor-dispatch-map-admin-candidate/entry-budgets.json"
        ).read_text()
    )
    legacy = consumer.model_validate(old)
    assert legacy.generation_budgets is None and legacy.model_dump(mode="json") == old
    if site == "map":
        budget.check_deployment_budgets(raw)
        legacy.check_deployment_budgets(old)
        with pytest.raises(ValueError):
            budget.check_deployment_budgets(old)


@pytest.mark.parametrize(
    "site,consumer", [("map", MapProductionBudgets), ("admin", AdminProductionBudgets)]
)
@pytest.mark.parametrize("change", ["missing", "legacy", "mismatch", "too-large"])
def test_invalid_budget_selection_rejected_before_runtime_effects(
    site: str, consumer: Any, change: str
) -> None:
    package = (
        "framework-map-navigation42-production-20261102-v1"
        if site == "map"
        else "framework-admin-navigation-production-20261102-v1"
    )
    raw = json.loads(
        (
            W
            / "experiments"
            / package
            / "runtime-actor-dispatch-windows-candidate/entry-budgets.json"
        ).read_text()
    )
    if change == "missing":
        del raw["generation_budgets"]
    elif change == "legacy":
        raw["schema_version"] = raw["schema_version"].replace("/5", "/4")
    elif change == "mismatch":
        raw["generation_budgets"]["execution_seconds"] = 599
    else:
        raw["generation_budgets"]["preparation_seconds"] = 3600
    with pytest.raises(ValueError):
        consumer.model_validate(raw)


@pytest.mark.parametrize(
    "site,consumer", [("map", MapProductionBudgets), ("admin", AdminProductionBudgets)]
)
def test_selected_return_budget_is_in_actual_round_reserve(
    site: str, consumer: Any
) -> None:
    package = (
        "framework-map-navigation42-production-20261102-v1"
        if site == "map"
        else "framework-admin-navigation-production-20261102-v1"
    )
    raw = json.loads(
        (
            W
            / "experiments"
            / package
            / "runtime-actor-return-pinned-candidate/entry-budgets.json"
        ).read_text()
    )
    selected = consumer.model_validate(raw)
    assert selected.generation_budgets.retention_seconds == 300
    assert selected.model_dump(mode="json") == raw
    required = selected.generation_budgets.round_seconds(
        selected.interaction_seconds, selected.actor_rpc_cleanup_seconds
    )
    assert required <= selected.stage_budgets.actor_seconds
    raw["generation_budgets"]["preparation_seconds"] = (
        selected.stage_budgets.actor_seconds
        - selected.interaction_seconds
        - 5 * selected.actor_rpc_cleanup_seconds
        - selected.generation_seconds
    )
    # Old formula would fit exactly, but explicit retention must reject.
    with pytest.raises(ValueError):
        consumer.model_validate(raw)
