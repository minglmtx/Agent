"""Original source catalogue is a refusal/minimal-input index, never a grant."""

import json
from pathlib import Path
from typing import Any
import pytest
import admin_production_entry as admin
import admin_production_inputs as admin_inputs
import admin_production_deployment as admin_deployment
import production_entry as maps
import production_inputs as map_inputs
import production_deployment as map_deployment
from types import SimpleNamespace
from lab_generate_skill.bootstrap.source_construction_inputs import (
    source_construction_inputs,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from admin_production_task_plan import AdminProductionBudgets
from production_task_plan import MapProductionBudgets
from test_source_material_entry import original, selected_admin
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "pending",
        "ready",
        "historical",
        "unknown",
        "prior",
        "partial",
        "missing",
        "duplicate",
        "type",
        "applicability",
        "cancel",
    ],
)
def test_catalogue_reuses_common_inputs_and_only_requests_missing_current_task_facts(
    tmp_path: Path, fault: str
) -> None:
    _, material, _ = original("admin")
    task = material.browser.configuration.spec.scope.task
    source: dict[str, Any] = {"id": "member.source", "status": "未开始", "evidence": []}
    member: dict[str, Any] = {
        "source_task_id": task.source_task_id,
        "historical": False,
        "attempt_job": "33",
        "checkpoints": [source],
    }
    if fault == "ready":
        source["status"] = "通过"
    elif fault == "historical":
        member["historical"] = True
    elif fault == "unknown":
        source["status"] = "未确认"
    elif fault == "prior":
        member["attempt_job"] = "22"
    elif fault == "partial":
        source["evidence"] = ["original/partial.json"]
    elif fault == "duplicate":
        member["checkpoints"] = [source, dict(source)]
    elif fault == "applicability":
        member["historical"] = None
    members: Any = {} if fault == "none" else {"selected": member}
    if fault == "type":
        members = []
    body = (
        {}
        if fault == "missing"
        else {"group_execution_plan": {"evidence_checkpoints": {"members": members}}}
    )
    plan = tmp_path / "batch-plan.json"
    plan.write_text(json.dumps(body))
    raw = plan.read_bytes()
    control: Any = guard(30)
    if fault == "cancel":

        class Stop:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "source-index")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        control = Stop()
    if fault in {"none", "pending"}:
        needs = source_construction_inputs(plan, task, "33", control)
        assert len(needs["required_new_facts"]) == 4 and len(needs["reuse"]) == 2
        assert (
            needs["source_task_id"] == task.source_task_id
            and needs["runtime_or_resume_authority"] is False
        )
    else:
        with pytest.raises((ValueError, OwnershipConflict, OperationStopped)):
            source_construction_inputs(plan, task, "33", control)
    assert plan.read_bytes() == raw and list(tmp_path.iterdir()) == [plan]


@pytest.mark.parametrize("site", ["admin", "map"])
def test_actual_entry_cannot_omit_indexed_historical_source_and_default_to_rebuilding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, site: str
) -> None:
    _, material, runtime = original(site)
    task = material.browser.configuration.spec.scope.task
    monkeypatch.setenv("LAB_JOB_OUTPUT_DIRECTORY", str(tmp_path))
    job = OperationWindowBudgets.model_validate_json(
        (runtime / "job-budgets.json").read_bytes()
    )
    recovery = SourceRecoveryBudgets.model_validate_json(
        (runtime / "source-recovery-budgets.json").read_bytes()
    )
    if site == "admin":
        selected = selected_admin(material)
        monkeypatch.setattr(
            admin_inputs, "load_admin_navigation_group", lambda control: (selected,)
        )

        def forbidden(*a: Any, **kw: Any) -> Any:
            raise AssertionError(
                "Historical source omission reached deployment/resources"
            )

        monkeypatch.setattr(admin_deployment, "load_admin_deployment", forbidden)
        with pytest.raises(OwnershipConflict, match="historical"):
            admin.run_admin_navigation(
                task.source_task_id,
                tmp_path / "deployment.json",
                budgets=AdminProductionBudgets.model_validate_json(
                    (runtime / "entry-budgets.json").read_bytes()
                ),
                job_budgets=job,
                recovery_budgets=recovery,
                origin=None,
                allowed_actions=("send_msg_to_user",),
            )
    else:
        monkeypatch.setattr(maps, "selected_navigation", map_inputs.declared_navigation)
        monkeypatch.setattr(
            map_deployment,
            "choose_deployment",
            lambda *a, **kw: SimpleNamespace(path=tmp_path / "must-not-read.json"),
        )
        with pytest.raises(OwnershipConflict, match="historical"):
            maps.run(
                task.source_task_id,
                tmp_path / "deployment.json",
                entry_budgets=MapProductionBudgets.model_validate_json(
                    (runtime / "entry-budgets.json").read_bytes()
                ),
                job_budgets=job,
                recovery_budgets=recovery,
            )
