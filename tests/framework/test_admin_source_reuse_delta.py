"""Exact original Admin inputs at the production branch and resource boundary."""

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
import admin_production_entry as entry
import admin_production_inputs as inputs
import admin_production_deployment as deployment
import admin_production_supply as supply
from lab_generate_skill.bootstrap.admin_source_reuse_inputs import (
    prepare_admin_source_delta,
    load_admin_source_delta,
    require_admin_source_unclaimed,
)
from lab_generate_skill.domain.claims import SourceClaimKey
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from admin_production_task_plan import AdminProductionBudgets
from test_source_material_entry import W, original, selected_admin
from test_slurm_commands import guard

C = W / "experiments/framework-combined-release-20261030-v1"
A = W / "experiments/framework-admin-navigation-production-20261102-v1"
R = A / "runtime-source-reuse-delta-candidate"


def delta_for(
    source_id: str, control: Any, complete: Path | None = None
) -> dict[str, Any]:
    return prepare_admin_source_delta(
        C / "admin71-source-inventory-4955227/inventory.json",
        C / "admin71-source-compatibility-4955261/compatibility.json",
        source_id,
        (C / "source-reuse-delta-source-fixtures-4954645/scoped-acceptance.json",),
        control,
        complete_material=complete,
    )


def write_delta(path: Path, delta: dict[str, Any]) -> str:
    path.write_text(json.dumps(delta))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("complete", [False, True])
def test_exact_selected_body_reaches_consumer_without_group_or_historical_reread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    complete: bool,
) -> None:
    _, material, _ = original("admin")
    sid = material.browser.configuration.spec.scope.task.source_task_id
    expected = selected_admin(material)
    complete_path = tmp_path / "complete.json"
    complete_path.write_text(material.model_dump_json())
    control = guard(60)
    delta = delta_for(sid, control, complete_path if complete else None)
    path = tmp_path / "delta.json"
    sha = write_delta(path, delta)
    physical = Path.open
    forbidden = {
        Path(x["path"])
        for x in delta["found_artifacts"]
        if x["kind"] != "native_contract"
    }
    reads: list[Path] = []

    def read(p: Path, *args: Any, **kw: Any) -> Any:
        assert p not in forbidden, "Reused original historical artifact was reopened"
        reads.append(p)
        return physical(p, *args, **kw)

    monkeypatch.setattr(Path, "open", read)
    loaded = load_admin_source_delta(path, sha, sid, control)
    assert (
        inputs.SelectedAdminNavigation(
            loaded.raw, loaded.reference, loaded.private, loaded.goal
        )
        == expected
    )
    assert loaded.material == (material if complete else None)
    assert reads.count(Path(delta["native_contract"]["path"])) == 1
    assert reads.count(Path(delta["compatibility"]["path"])) == 1
    assert loaded.delta["execution"]["source_producer_calls"] == (0 if complete else 1)
    assert loaded.delta["execution"]["historical_validator_calls"] == 0
    assert loaded.delta["execution"]["common_check_or_install_calls"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "pin",
        "native",
        "review",
        "mode",
        "supplement",
        "history",
        "common",
        "private",
        "goal",
        "task",
        "grant",
        "complete_missing",
    ],
)
def test_invalid_delta_never_falls_back_to_reconstruction(
    tmp_path: Path, fault: str
) -> None:
    _, material, _ = original("admin")
    sid = material.browser.configuration.spec.scope.task.source_task_id
    control = guard(60)
    delta = delta_for(sid, control)
    if fault == "native":
        delta["native_contract"]["sha256"] = "0" * 64
    elif fault == "review":
        delta["compatibility"]["sha256"] = "0" * 64
    elif fault == "mode":
        delta["execution"]["mode"] = "build_all"
    elif fault == "supplement":
        delta["execution"]["supplement"] = []
    elif fault == "history":
        delta["found_artifacts"] = []
    elif fault == "common":
        delta["common_evidence"] = []
    elif fault == "private":
        delta["private_spec"]["target_path"] = "/wrong/"
    elif fault == "goal":
        delta["public_goal"] = "Substituted goal"
    elif fault == "task":
        delta["source_task_id"] = "other"
    elif fault == "grant":
        delta["runtime_or_resume_authority"] = True
    elif fault == "complete_missing":
        delta["complete_material"] = {
            "path": str(tmp_path / "missing.json"),
            "sha256": "0" * 64,
            "size_bytes": 1,
        }
        delta["execution"].update(
            mode="consume_complete", supplement=[], source_producer_calls=0
        )
    path = tmp_path / "delta.json"
    sha = write_delta(path, delta)
    with pytest.raises((ValueError, OwnershipConflict, FileNotFoundError)):
        load_admin_source_delta(path, "0" * 64 if fault == "pin" else sha, sid, control)


def budgets() -> dict[str, Any]:
    return {
        "budgets": AdminProductionBudgets.model_validate_json(
            (R / "entry-budgets.json").read_bytes()
        ),
        "job_budgets": OperationWindowBudgets.model_validate_json(
            (R / "job-budgets.json").read_bytes()
        ),
        "recovery_budgets": SourceRecoveryBudgets.model_validate_json(
            (R / "source-recovery-budgets.json").read_bytes()
        ),
        "origin": None,
        "allowed_actions": ("click", "send_msg_to_user"),
    }


@pytest.mark.parametrize("fault", ["half_delta", "pin", "claim", "material_conflict"])
def test_actual_entry_rejects_before_group_deployment_metadata_or_resource(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    _, material, _ = original("admin")
    sid = material.browser.configuration.spec.scope.task.source_task_id
    path = tmp_path / "delta.json"
    sha = write_delta(path, delta_for(sid, guard(60)))
    root = tmp_path / "source-claims"
    root.mkdir()
    monkeypatch.setattr(entry, "PACKAGE", tmp_path)

    def forbidden(*a: Any, **kw: Any) -> Any:
        pytest.fail("Invalid delta reached original group/deployment/resource work")

    monkeypatch.setattr(inputs, "load_admin_navigation_group", forbidden)
    monkeypatch.setattr(deployment, "load_admin_deployment", forbidden)
    monkeypatch.setattr(supply, "supply_admin_runtime", forbidden)
    if fault == "claim":
        key = SourceClaimKey(
            scope_id="admin-navigation71-engineering-once", source_task_id=sid
        )
        (root / (key.filename + ".reserved")).write_text("uncertain")
    args: dict[str, Any] = {"source_delta_path": path}
    if fault != "half_delta":
        args["source_delta_sha256"] = "0" * 64 if fault == "pin" else sha
    if fault == "material_conflict":
        args["source_material"] = material
    with pytest.raises(OwnershipConflict):
        entry.run_admin_navigation(
            sid, tmp_path / "deployment.json", **budgets(), **args
        )


@pytest.mark.parametrize("complete", [False, True])
def test_actual_entry_passes_selected_body_and_source_branch_to_original_supplier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    complete: bool,
) -> None:
    _, material, _ = original("admin")
    sid = material.browser.configuration.spec.scope.task.source_task_id
    expected = selected_admin(material)
    complete_path = tmp_path / "complete.json"
    complete_path.write_text(material.model_dump_json())
    path = tmp_path / "delta.json"
    delta = delta_for(sid, guard(60), complete_path if complete else None)
    sha = write_delta(path, delta)
    (tmp_path / "source-claims").mkdir()
    monkeypatch.setattr(entry, "PACKAGE", tmp_path)
    monkeypatch.setenv("LAB_JOB_OUTPUT_DIRECTORY", str(tmp_path))
    calls: list[str] = []

    def forbidden(*a: Any, **kw: Any) -> Any:
        pytest.fail("Selected delta reloaded the whole group")

    monkeypatch.setattr(inputs, "load_admin_navigation_group", forbidden)
    monkeypatch.setattr(
        deployment, "load_admin_deployment", lambda *a: SimpleNamespace()
    )
    import lab_generate_skill.bootstrap.source_construction_inputs as construction

    def needs(*a: Any) -> dict[str, Any]:
        calls.append("current-instance-needs")
        assert not complete and a[1] == expected.private.task
        return {"task": sid}

    monkeypatch.setattr(construction, "source_construction_inputs", needs)
    facts: dict[str, Any] = {}

    @contextmanager
    def supplied(selected: Any, *a: Any, **kw: Any) -> Any:
        calls.append("supply")
        assert selected == expected
        assert kw.get("source_material") == (material if complete else None)
        yield SimpleNamespace(facts=facts, runtime=SimpleNamespace(selected=selected))

    def execute(selected: Any, runtime: Any) -> dict[str, Any]:
        calls.append("sole-original-task-execution")
        assert selected == expected and runtime.selected is selected
        return {"boundary": "original-execution-constructor"}

    monkeypatch.setattr(supply, "supply_admin_runtime", supplied)
    monkeypatch.setattr(entry, "execute_admin_navigation", execute)
    result = entry.run_admin_navigation(
        sid,
        tmp_path / "deployment.json",
        **budgets(),
        source_delta_path=path,
        source_delta_sha256=sha,
    )
    assert calls == ([] if complete else ["current-instance-needs"]) + [
        "supply",
        "sole-original-task-execution",
    ]
    assert result["source_reuse_delta"] == delta
    assert result["source_reuse_calls"] == {
        "historical_validator": 0,
        "common_check_or_install": 0,
        "source_producer": 0 if complete else 1,
    }


def test_cancelled_read_and_uncertain_claim_are_refusals(tmp_path: Path) -> None:
    class Cancelled:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "admin-source-delta")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped):
        require_admin_source_unclaimed(tmp_path, "original", Cancelled())
    key = SourceClaimKey(
        scope_id="admin-navigation71-engineering-once", source_task_id="original"
    )
    (tmp_path / (key.filename + ".reserved")).write_text("uncertain")
    with pytest.raises(OwnershipConflict):
        require_admin_source_unclaimed(tmp_path, "original", guard(60))
