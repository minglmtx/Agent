"""Family configuration composes with the real single-member outer wrappers."""

from datetime import timedelta
import json
from pathlib import Path
import re
from typing import Any

import pytest
from pydantic import ValidationError

from admin_production_task_plan import AdminProductionBudgets
from production_task_plan import MapProductionBudgets
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from test_bounded_lifecycle import owner
from test_lifecycle import ManualClock

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
FAMILIES = (
    ("framework-map-navigation42-production-20261102-v1", MapProductionBudgets),
    ("framework-admin-navigation-production-20261102-v1", AdminProductionBudgets),
)


@pytest.mark.parametrize("package,kind", FAMILIES)
def test_exact_family_recipe_and_wrapper(package: str, kind: Any) -> None:
    root = W / "experiments" / package
    runtime = root / "runtime-repair-candidate"
    selected = kind.model_validate_json((runtime / "entry-budgets.json").read_bytes())
    job = OperationWindowBudgets.model_validate_json(
        (runtime / "job-budgets.json").read_bytes()
    )
    recovery = SourceRecoveryBudgets.model_validate_json(
        (runtime / "source-recovery-budgets.json").read_bytes()
    )
    basis = json.loads(
        (root / "runtime-planning/repair-budget-basis.json").read_bytes()
    )
    wrapper = (runtime / "production-budget.sbatch").read_text()
    match = re.search(r"^#SBATCH --time=(\d+):(\d+):(\d+)$", wrapper, re.M)
    assert match is not None
    wall = sum(
        int(x) * unit for x, unit in zip(match.groups(), (3600, 60, 1), strict=True)
    )
    assert wall == basis["wall_seconds"]
    assert (
        wall
        >= job.minimum_remaining_seconds + basis["pre_window_setup_allowance_seconds"]
    )
    assert f"#SBATCH --signal=B:USR1@{job.stop_signal_lead_seconds}" in wrapper
    assert job.execution_seconds == selected.root_seconds
    assert (
        selected.required_pre_claim_seconds
        == selected.post_claim_setup_seconds + selected.task_seconds
    )
    assert sum(basis["execution_estimates"].values()) <= job.execution_seconds
    assert (
        recovery.complete_recovery_path_seconds + recovery.preparation_metadata_seconds
        <= job.cleanup_seconds
    )
    assert (
        job.stop_signal_lead_seconds >= job.cleanup_seconds + job.final_margin_seconds
    )
    clock = ManualClock()
    window = job.window(
        owner(), now=clock.utcnow(), hard_end=clock.utcnow() + timedelta(seconds=wall)
    )
    assert (
        window.cleanup_deadline - window.execution_deadline
    ).total_seconds() >= job.cleanup_seconds
    assert "runtime-repair-candidate" in wrapper
    assert "lab-generate-skill-group-owner-candidate-20261104" in wrapper
    assert "kill -USR1" in wrapper and "kill -TERM" in wrapper


@pytest.mark.parametrize("package,kind", FAMILIES)
def test_legacy_wire_is_unchanged_but_cannot_admit_current_entry(
    package: str, kind: Any
) -> None:
    legacy = kind()
    assert "post_claim_setup_seconds" not in legacy.model_dump()
    assert "post_claim_setup_seconds" not in legacy.model_dump_json(exclude_none=True)
    with pytest.raises(ValueError, match="explicit"):
        _ = legacy.required_pre_claim_seconds
    with pytest.raises(ValidationError):
        kind(post_claim_setup_seconds=1)
    with pytest.raises(ValidationError):
        kind(schema_version=legacy.schema_version.replace("/1", "/2"))


@pytest.mark.parametrize("value", [None, True, 0, -1, 7201, 1.5, "3"])
@pytest.mark.parametrize("package,kind", FAMILIES)
def test_bad_setup_and_composition_rejected(
    package: str, kind: Any, value: Any
) -> None:
    raw = json.loads(
        (
            W / "experiments" / package / "runtime-repair-candidate/entry-budgets.json"
        ).read_bytes()
    )
    with pytest.raises(ValidationError):
        kind.model_validate({**raw, "post_claim_setup_seconds": value})
    with pytest.raises(ValidationError):
        kind.model_validate(
            {**raw, "root_seconds": raw["site_seconds"] + raw["task_seconds"]}
        )
