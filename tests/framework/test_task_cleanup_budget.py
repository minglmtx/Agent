"""Original frozen RunPlan budget, never an implicit component timeout increase."""

from pathlib import Path
import pytest
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from task_execution_fixtures import task_case
import construction_storage_fixtures as construction_data
from test_evidence_run_plans import persisted_plan
from evidence_control_fixtures import EvidenceFixtureStore
from lab_generate_skill.domain.run_plan import RunPlan


def test_task_cleanup_cannot_exceed_original_run_before_any_effect(
    tmp_path: Path,
) -> None:
    c = task_case(tmp_path / "task")
    before = c.deps.runs.read(c.plan.read_operation)
    plan = TaskExecutionPlan.model_validate(
        c.plan.model_copy(update={"cleanup_seconds": 61})
    )
    with pytest.raises(OwnershipConflict, match="original frozen RunPlan budget"):
        execute_task(plan, c.deps)
    assert c.deps.runs.read(c.plan.read_operation) == before and not c.phases.calls
    assert c.model.calls == c.browser.calls == 0


def test_explicit_frozen_larger_task_budget_does_not_change_actor_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = persisted_plan

    def configured(store: EvidenceFixtureStore) -> RunPlan:
        run = original(store)
        return run.model_copy(
            update={
                "resources": run.resources.model_copy(
                    update={"cleanup_timeout_seconds": 600}
                )
            }
        )

    with monkeypatch.context() as patch:
        patch.setattr(construction_data, "persisted_plan", configured)
        c = task_case(tmp_path / "task")
    actor_cleanup = c.phases.initialized.actor.cleanup_seconds
    plan = TaskExecutionPlan.model_validate(
        c.plan.model_copy(update={"cleanup_seconds": 600})
    )
    result = execute_task(plan, c.deps)
    assert result.evaluation.status == "failure"
    assert c.phases.initialized.actor.cleanup_seconds == actor_cleanup <= 60
    assert c.model.calls == c.browser.calls == 1
