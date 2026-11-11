"""Real supplier DTO and original phase consumer wiring; no website qualification."""

from dataclasses import replace
import inspect
from pathlib import Path
from typing import Any
import pytest
from pydantic import TypeAdapter
from lab_generate_skill.domain.execution_stage_budget import ExecutionStageBudgets
from lab_generate_skill.bootstrap.shopping_category_runtime_supply import (
    CategoryNavigationSupplierInputs,
    supply_category_runtime,
)
from lab_generate_skill.bootstrap.shopping_category_production_entry import (
    run_category_production,
)
from lab_generate_skill.bootstrap.shopping_category_production_member import (
    execute_claimed_category_member,
)
from lab_generate_skill.bootstrap import shopping_category_cli as cli


@pytest.fixture(scope="module")
def original() -> CategoryNavigationSupplierInputs:
    # Exact retained producer bytes are only schema fixtures, never authority for this candidate.
    path = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-combined-release-20261030-v1/runtime-shopping-source-graph-candidate/install-4931728/a40/supplier-inputs.json"
    )
    return TypeAdapter(CategoryNavigationSupplierInputs).validate_json(
        path.read_bytes()
    )


def stages() -> ExecutionStageBudgets:
    return ExecutionStageBudgets(
        assets_seconds=600,
        source_seconds=4200,
        model_seconds=1200,
        preparation_seconds=1800,
        initialization_seconds=2100,
        actor_seconds=3600,
        capture_seconds=600,
        judgment_seconds=300,
        task_orchestration_seconds=300,
    )


def test_real_supplier_dto_round_trip_explicit_composition_and_legacy_bytes(
    original: CategoryNavigationSupplierInputs,
) -> None:
    s = replace(original, task_seconds=8700, setup_seconds=1200, stage_budgets=stages())
    adapter = TypeAdapter(CategoryNavigationSupplierInputs)
    checked = adapter.validate_json(adapter.dump_json(s, exclude_none=True))
    assert checked == s and checked.stage_budgets is not None
    assert (
        checked.stage_budgets.execution_seconds <= checked.job_budgets.execution_seconds
    )
    assert checked.stage_budgets.actor_seconds == 3600
    assert (
        checked.engine.context_window,
        checked.parameters.max_input_tokens,
        checked.parameters.max_new_tokens,
    ) == (65536, 61440, 4096)
    legacy = adapter.dump_json(original, exclude_none=True)
    assert (
        b'"stage_budgets"' not in legacy
        and adapter.validate_json(legacy).stage_budgets is None
    )


@pytest.mark.parametrize(
    "field,bad",
    [("task_seconds", 8701), ("setup_seconds", 1199), ("site_seconds", 4100)],
)
def test_mismatched_supplier_stage_budget_refused_at_construction_before_effects(
    original: CategoryNavigationSupplierInputs, field: str, bad: int
) -> None:
    s = replace(original, task_seconds=8700, setup_seconds=1200, stage_budgets=stages())
    with pytest.raises(ValueError, match="phase budgets"):
        if field == "task_seconds":
            replace(s, task_seconds=bad)
        elif field == "setup_seconds":
            replace(s, setup_seconds=bad)
        else:
            replace(s, site_seconds=bad)
    with pytest.raises(ValueError, match="phase budgets"):
        replace(
            s, job_budgets=s.job_budgets.model_copy(update={"execution_seconds": 14000})
        )


def test_current_cli_refuses_legacy_budget_before_native_documents_or_runtime(
    original: CategoryNavigationSupplierInputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = TypeAdapter(CategoryNavigationSupplierInputs)
    raw = adapter.dump_json(original, exclude_none=True)
    reads = []

    def document(path: Path) -> bytes:
        reads.append(path)
        if path != Path("/supplier"):
            pytest.fail("No native/site access without explicit phase selection")
        return raw

    monkeypatch.setattr(cli, "_document", document)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Legacy configuration reached runtime supplier")

    monkeypatch.setattr(cli, "supply_category_runtime", forbidden)
    monkeypatch.setattr(
        "sys.argv",
        [
            "category",
            "--supplier-inputs",
            "/supplier",
            "--native-input",
            "/native",
            "--native-reference",
            "/reference",
            "--public-task",
            "/public",
            "--output",
            "/output",
            "--claim-root",
            "/claims",
            "--claim-scope",
            "unit",
        ],
    )
    with pytest.raises(ValueError, match="explicit stage budgets"):
        cli.main()
    assert reads == [Path("/supplier")]


def test_real_affected_callers_are_the_selected_stage_consumers() -> None:
    supplier = inspect.unwrap(supply_category_runtime)
    assert {"configure_stages", "execution_stage", "require_execution_budget"} <= set(
        supplier.__code__.co_names
    )
    assert "execution_stage" in run_category_production.__code__.co_names
    assert {"execution_stage", "ExitStack"} <= set(
        execute_claimed_category_member.__code__.co_names
    )
