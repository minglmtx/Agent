"""Actual Map consumer refuses pinned/configured limits diverging from deployment."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
import production_entry as entry
import production_deployment as deployment
from production_task_plan import MapProductionBudgets
from production_inputs import declared_navigation
import lab_generate_skill.bootstrap.source_construction_inputs as source_inputs
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets

RUNTIME = Path(entry.__file__).resolve().parent


@pytest.mark.parametrize(
    "fault", ["none", "old_limits", "missing", "schema", "type", "extra"]
)
def test_actual_entry_compares_complete_frozen_limits_before_installation_or_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    raw: dict[str, Any] = json.loads((RUNTIME / "entry-budgets.json").read_bytes())
    selected = MapProductionBudgets.model_validate(raw)
    actual = dict(raw)
    if fault == "old_limits":
        actual.update(task_seconds=4800, post_claim_setup_seconds=4500)
    elif fault == "missing":
        del actual["storage_io_seconds"]
    elif fault == "schema":
        actual.update(schema_version="map-production-budgets/1")
        del actual["post_claim_setup_seconds"]
    elif fault == "type":
        actual["task_seconds"] = True
    elif fault == "extra":
        actual["unreviewed_budget"] = 1
    path = tmp_path / "deployment.json"
    path.write_text(
        json.dumps(
            {
                "passed": True,
                "formal_training_qualification": False,
                "budgets": actual,
                "software_path": str(tmp_path / "software.json"),
            }
        )
    )
    monkeypatch.setenv("LAB_JOB_OUTPUT_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(
        deployment, "choose_deployment", lambda *a, **kw: SimpleNamespace(path=path)
    )
    # The real producer shape is required by the new read-only group-index
    # preflight. This test stops at installation, before any source or claim.
    selected_task = declared_navigation("6e27e10e6049cee4f85d")
    monkeypatch.setattr(entry, "selected_navigation", lambda source: selected_task)
    preprocessed: list[object] = []

    def index_before_installation(
        path: Any, task: Any, job: Any, control: Any
    ) -> dict[str, Any]:
        control.checkpoint()
        assert task == selected_task.public_template.identity
        preprocessed.append(task)
        return {"fixture": "read-only-index-premise-no-runtime-grant"}

    monkeypatch.setattr(
        source_inputs, "source_construction_inputs", index_before_installation
    )
    reached: list[str] = []

    class InstallationBoundary(Exception):
        pass

    def installation(*args: Any, **kwargs: Any) -> None:
        reached.append("installation")
        raise InstallationBoundary()

    monkeypatch.setattr(entry, "verify_source", installation)
    with pytest.raises(InstallationBoundary if fault == "none" else ValueError):
        entry.run(
            selected_task.public_template.identity.source_task_id,
            path,
            entry_budgets=selected,
            job_budgets=OperationWindowBudgets.model_validate_json(
                (RUNTIME / "job-budgets.json").read_bytes()
            ),
            recovery_budgets=SourceRecoveryBudgets.model_validate_json(
                (RUNTIME / "source-recovery-budgets.json").read_bytes()
            ),
        )
    assert reached == (["installation"] if fault == "none" else [])
    assert preprocessed == [selected_task.public_template.identity]
    assert not (tmp_path / "member-result.json").exists()
