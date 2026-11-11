"""Configuration-only reserve rebalance, same outer limits and single member."""

import json
from pathlib import Path
import subprocess
import pytest
from production_task_plan import MapProductionBudgets
from admin_production_task_plan import AdminProductionBudgets
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


@pytest.mark.parametrize(
    "package,kind,task,source",
    [
        (
            "framework-map-navigation42-production-20261102-v1",
            MapProductionBudgets,
            7200,
            6000,
        ),
        (
            "framework-admin-navigation-production-20261102-v1",
            AdminProductionBudgets,
            6600,
            4200,
        ),
    ],
)
def test_actual_family_budgets_preserve_outer_cleanup_and_whole_task_cap(
    package: str,
    kind: type[MapProductionBudgets] | type[AdminProductionBudgets],
    task: int,
    source: int,
) -> None:
    root = W / "experiments" / package
    runtime = root / "runtime-initialization-input-binding-candidate"
    old = root / "runtime-context-inputs-candidate"
    selected = kind.model_validate_json((runtime / "entry-budgets.json").read_bytes())
    job = OperationWindowBudgets.model_validate_json(
        (runtime / "job-budgets.json").read_bytes()
    )
    recovery = SourceRecoveryBudgets.model_validate_json(
        (runtime / "source-recovery-budgets.json").read_bytes()
    )
    assert selected.task_seconds == task and selected.site_seconds == source
    assert selected.post_claim_setup_seconds == 2400
    assert selected.required_pre_claim_seconds == 2400 + task
    assert source + 1800 + selected.required_pre_claim_seconds <= job.execution_seconds
    assert selected.root_seconds == job.execution_seconds
    for name in ("job-budgets.json", "source-recovery-budgets.json"):
        assert (runtime / name).read_bytes() == (old / name).read_bytes()
    assert (
        job.cleanup_seconds
        >= recovery.complete_recovery_path_seconds
        + recovery.preparation_metadata_seconds
    )
    script = (runtime / "production-budget.sbatch").read_text()
    assert "#SBATCH --signal=B:USR1@4800" in script
    assert "#SBATCH --time=" + ("06:15:00" if source == 6000 else "05:35:00") in script
    assert "[[ $# == 3 ]] || exit 64" in script
    result = subprocess.run(
        ["/bin/bash", "-n", str(runtime / "production-budget.sbatch")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    old_entry = json.loads((old / "entry-budgets.json").read_bytes())
    current = selected.model_dump()
    for name in ("post_claim_setup_seconds", "task_seconds"):
        old_entry.pop(name)
        current.pop(name)
    assert current == old_entry
