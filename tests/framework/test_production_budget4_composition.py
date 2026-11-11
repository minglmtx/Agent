"""Actual selected production budget consumers; no site/model/claim acquisition."""

import json
from pathlib import Path
from typing import Any
import pytest
from admin_production_task_plan import AdminProductionBudgets
from production_task_plan import MapProductionBudgets
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


@pytest.mark.parametrize(
    "site,consumer,task,root,prep,slurm",
    [
        ("admin", AdminProductionBudgets, 10200, 16500, 1800, "06:30:00"),
        ("map", MapProductionBudgets, 11700, 18900, 3300, "07:10:00"),
    ],
)
def test_explicit_budget4_preserves_component_caps_and_complete_job_window(
    site: str, consumer: Any, task: int, root: int, prep: int, slurm: str
) -> None:
    dirname = (
        "framework-admin-navigation-production-20261102-v1"
        if site == "admin"
        else "framework-map-navigation42-production-20261102-v1"
    )
    runtime = (
        W / "experiments" / dirname / "runtime-initial-observation-handoff-candidate"
    )
    raw = json.loads((runtime / "entry-budgets.json").read_bytes())
    budget = consumer.model_validate(raw)
    job = OperationWindowBudgets.model_validate_json(
        (runtime / "job-budgets.json").read_bytes()
    )
    recovery = SourceRecoveryBudgets.model_validate_json(
        (runtime / "source-recovery-budgets.json").read_bytes()
    )
    assert budget.task_cleanup_budget_seconds == 1800
    assert budget.metadata_cleanup_seconds == 300
    assert budget.stage_budgets.initialization_seconds == 3600
    assert budget.stage_budgets.preparation_seconds == prep
    assert budget.stage_budgets.task_seconds == budget.task_seconds == task
    assert (
        budget.stage_budgets.execution_seconds
        <= budget.root_seconds
        == root
        == job.execution_seconds
    )
    assert budget.storage_io_seconds == 30 and budget.storage_cleanup_seconds == 60
    assert budget.native_close_seconds == budget.actor_rpc_cleanup_seconds == 60
    assert budget.stage_budgets.actor_seconds == 3600
    assert budget.generation_seconds == 600 and budget.interaction_seconds == 180
    assert job.cleanup_seconds == 6000 and job.final_margin_seconds == 600
    assert job.stop_signal_lead_seconds == 6600
    # The original source abort path has no acquired model. The candidate path
    # includes one task window, site, trace read, Actor close, final read/review.
    candidate_path = 1800 + 300 + 300 + 300 + 60 + 660
    assert (
        max(candidate_path, recovery.complete_recovery_path_seconds)
        < job.cleanup_seconds
    )
    hours, minutes, seconds = map(int, slurm.split(":"))
    assert job.minimum_remaining_seconds + 300 == hours * 3600 + minutes * 60 + seconds
    wrapper = (runtime / "production-budget.sbatch").read_text()
    assert "#SBATCH --time=" + slurm in wrapper and "USR1@6600" in wrapper
    assert budget.model_dump(mode="json") == raw
    if site == "map":
        budget.check_deployment_budgets(raw)
    missing = {k: v for k, v in raw.items() if k != "task_cleanup_seconds"}
    with pytest.raises(ValueError):
        consumer.model_validate(missing)
    legacy = dict(missing, schema_version=raw["schema_version"].replace("/4", "/3"))
    old = consumer.model_validate(legacy)
    assert old.task_cleanup_budget_seconds == 300
    assert old.model_dump(mode="json") == legacy
