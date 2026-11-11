"""Real discovered Map inputs, explicit branches, zero historical revalidation."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
import source_delta_entry as entry
import production_deployment
from lab_generate_skill.bootstrap.map_source_reuse_inputs import (
    prepare_map_source_delta,
    load_map_source_delta,
    require_map_source_unclaimed,
)
from lab_generate_skill.domain.claims import SourceClaimKey
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from production_task_plan import MapProductionBudgets
from test_source_material_entry import W, original
from test_slurm_commands import guard

C = W / "experiments/framework-combined-release-20261030-v1"
M = W / "experiments/framework-map-navigation42-production-20261102-v1"


def delta_for(
    source_id: str, control: Any, complete: Path | None = None
) -> dict[str, Any]:
    return prepare_map_source_delta(
        M / "group-plan.json",
        C / "map42-source-inventory-4953898/inventory.json",
        C / "map42-source-compatibility-4953964/compatibility.json",
        source_id,
        (C / "actor-return-pinned-check-4952363/scoped-acceptance.json",),
        control,
        complete_material=complete,
    )


@pytest.mark.parametrize("complete", [False, True])
def test_selected_delta_consumes_exact_inputs_without_historical_producer_or_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, complete: bool
) -> None:
    _, material, _ = original("map")
    source_id = material.browser.configuration.spec.scope.task.source_task_id
    complete_path = tmp_path / "material.json"
    if complete:
        complete_path.write_text(material.model_dump_json())
    control = guard(60)
    delta = delta_for(source_id, control, complete_path if complete else None)
    assert len(delta["found_artifacts"]) == 5
    assert delta["execution"]["historical_validator_calls"] == 0
    assert delta["execution"]["source_producer_calls"] == (0 if complete else 1)
    assert len(delta["execution"]["supplement"]) == (0 if complete else 4)
    path = tmp_path / "delta.json"
    path.write_text(json.dumps(delta))
    raw = path.read_bytes()
    physical = Path.open
    forbidden = {
        Path(item["path"])
        for item in delta["found_artifacts"]
        if item["kind"] != "native_contract"
    }
    reads: list[Path] = []

    def read(p: Path, *args: Any, **kwargs: Any) -> Any:
        assert p not in forbidden, "Reused historical artifacts were reopened"
        reads.append(p)
        return physical(p, *args, **kwargs)

    monkeypatch.setattr(Path, "open", read)
    loaded = load_map_source_delta(
        path, hashlib.sha256(raw).hexdigest(), source_id, control
    )
    assert loaded.selection.binding.source_task_id == source_id
    assert loaded.material == (material if complete else None)
    assert not any(p in forbidden for p in reads)
    assert reads.count(Path(delta["native_contract"]["path"])) == 1
    assert reads.count(Path(delta["compatibility"]["path"])) == 1
    assert loaded.delta["execution"]["common_check_or_install_calls"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "delta_pin",
        "native",
        "compatibility",
        "mode",
        "supplement",
        "complete_missing",
        "history_missing",
        "task",
        "permission",
    ],
)
def test_changed_or_missing_inputs_never_fall_back_to_full_rebuild(
    tmp_path: Path, fault: str
) -> None:
    source_id = "95155cf17818f58e8de1"
    control = guard(60)
    delta = delta_for(source_id, control)
    if fault == "native":
        delta["native_contract"] = {**delta["native_contract"], "sha256": "0" * 64}
    elif fault == "compatibility":
        delta["compatibility"]["sha256"] = "0" * 64
    elif fault == "mode":
        delta["execution"]["mode"] = "build_all"
    elif fault == "supplement":
        delta["execution"]["supplement"] = []
    elif fault == "complete_missing":
        delta["complete_material"] = {
            "path": str(tmp_path / "missing.json"),
            "sha256": "0" * 64,
            "size_bytes": 1,
        }
        delta["execution"].update(
            mode="consume_complete", supplement=[], source_producer_calls=0
        )
    elif fault == "history_missing":
        delta["found_artifacts"] = []
    elif fault == "task":
        delta["source_task_id"] = "other-task"
    path = tmp_path / "delta.json"
    path.write_text(json.dumps(delta))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if fault == "delta_pin":
        sha = "0" * 64
    if fault == "permission":
        root = tmp_path / "claims"
        root.mkdir()
        require_map_source_unclaimed(root, source_id, control)
        key = SourceClaimKey(
            scope_id="map-navigation42-engineering-once", source_task_id=source_id
        )
        (root / (key.filename + ".reserved")).write_text("uncertain")
        with pytest.raises(OwnershipConflict):
            require_map_source_unclaimed(root, source_id, control)
    else:
        with pytest.raises((ValueError, OwnershipConflict, FileNotFoundError)):
            load_map_source_delta(path, sha, source_id, control)


@pytest.mark.parametrize(
    "fault", ["no_delta", "bad_pin", "consumed_claim", "material_conflict"]
)
def test_actual_map_entry_refuses_invalid_delta_before_deployment_metadata_or_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    _, material, _ = original("map")
    runtime = M / "runtime-source-reuse-delta-candidate"
    source_id = material.browser.configuration.spec.scope.task.source_task_id
    path = tmp_path / "delta.json"
    path.write_text(json.dumps(delta_for(source_id, guard(60))))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "source-claims").mkdir()
    monkeypatch.setattr(entry, "PACKAGE", tmp_path)
    monkeypatch.setenv("LAB_JOB_OUTPUT_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(
        production_deployment,
        "choose_deployment",
        lambda *a, **kw: SimpleNamespace(path=tmp_path / "must-not-read.json"),
    )

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Invalid source delta reached expensive construction")

    monkeypatch.setattr(entry, "qualify_map_navigation_source", forbidden)
    monkeypatch.setattr(entry, "owner_metadata_store", forbidden)
    monkeypatch.setattr(entry, "source_browser_assets", forbidden)
    if fault == "consumed_claim":
        key = SourceClaimKey(
            scope_id="map-navigation42-engineering-once", source_task_id=source_id
        )
        (tmp_path / "source-claims" / key.filename).write_text("original-claim")
    args: dict[str, Any] = {}
    if fault != "no_delta":
        args.update(
            source_delta_path=path,
            source_delta_sha256="0" * 64 if fault == "bad_pin" else sha,
        )
    if fault == "material_conflict":
        args["source_material"] = material
    with pytest.raises(OwnershipConflict):
        entry.run(
            source_id,
            tmp_path / "deployment.json",
            entry_budgets=MapProductionBudgets.model_validate_json(
                (runtime / "entry-budgets.json").read_bytes()
            ),
            job_budgets=OperationWindowBudgets.model_validate_json(
                (runtime / "job-budgets.json").read_bytes()
            ),
            recovery_budgets=SourceRecoveryBudgets.model_validate_json(
                (runtime / "source-recovery-budgets.json").read_bytes()
            ),
            **args,
        )
