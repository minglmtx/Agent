"""Real retained producer formats at actual CLI/supplier boundaries.

CLI/join tests intercept resource execution. Original ended owners are rejected
by the real supplier before metadata/assets; no old source is reacquired.
"""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
import pytest
import admin_production_entry as admin
import admin_production_supply as supply
import admin_production_inputs as admin_inputs
import admin_production_deployment as admin_deployment
import production_entry as maps
import production_inputs as map_inputs
import production_deployment as map_deployment
from lab_generate_skill.bootstrap.source_material_input import load_source_material
from lab_generate_skill.adapters.plans.closed_source_protocol import decode_command
from lab_generate_skill.adapters.map_runtime.metadata import object_json
from lab_generate_skill.domain.closed_source_read import (
    ClosedAdminNavigationReadMaterial,
    ClosedMapReadMaterial,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    OperationStopped,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    declare_admin_navigation,
)
from test_admin_runtime_resource_supply import retained
from admin_production_deployment import check_admin_deployment, AdminDeployment
from admin_production_task_plan import AdminProductionBudgets
from production_task_plan import MapProductionBudgets
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
CASES: dict[str, tuple[str, int, Any]] = {
    "admin": (
        "framework-admin-navigation-production-20261102-v1",
        4928366,
        ClosedAdminNavigationReadMaterial,
    ),
    "map": (
        "framework-map-navigation42-production-20261102-v1",
        4928367,
        ClosedMapReadMaterial,
    ),
}


def original(site: str) -> tuple[bytes, Any, Path]:
    package, job, expected = CASES[site]
    root = W / "experiments" / package
    raw = (root / f"production-{job}/source-read/last-request.json").read_bytes()
    material = decode_command(raw).material
    assert isinstance(material, expected)
    return raw, material, root / "runtime-actor-return-pinned-candidate"


def selected_admin(
    material: Any, source_id: str | None = None
) -> admin_inputs.SelectedAdminNavigation:
    task = material.browser.configuration.spec.scope.task
    if source_id is not None:
        task = task.model_copy(
            update={"source_task_id": source_id, "task_id": source_id}
        )
    path = (
        W
        / "experiments/sft-admin-navigation-bindings-v1/prepared/sources"
        / task.source_task_id
        / "native-contract.json"
    )
    raw = path.read_bytes()
    native = object_json(raw)
    ref = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="admin-native-contract/1",
            visibility="private",
            producer="original-admin-navigation",
        ),
    )
    private = declare_admin_navigation(native, ref, task, native["goal"])
    return admin_inputs.SelectedAdminNavigation(raw, ref, private, native["goal"])


@pytest.mark.parametrize("site", ["admin", "map"])
@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "declarations",
        "sha",
        "site",
        "schema",
        "duplicate",
        "nonfinite",
        "missing",
        "alias",
        "cancel",
    ],
)
def test_original_pinned_material_file_refuses_mismatch_before_any_source_effect(
    tmp_path: Path, site: str, fault: str
) -> None:
    raw, material, _ = original(site)
    expected = CASES[site][2]
    path = tmp_path / "source.json"
    if fault == "declarations":
        body = material.model_dump(mode="json")
        if site == "map":
            body.pop("schema_version")
        raw = json.dumps(body).encode()
    elif fault == "site":
        expected = (
            ClosedMapReadMaterial
            if site == "admin"
            else ClosedAdminNavigationReadMaterial
        )
    elif fault == "schema":
        raw = raw.replace(
            b"closed-source-read-command/1", b"closed-source-read-command/9"
        )
    elif fault == "duplicate":
        raw = b'{"a":1,"a":2}'
    elif fault == "nonfinite":
        raw = b'{"a":NaN}'
    path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    if fault == "sha":
        sha = "0" * 64
    elif fault == "missing":
        path.unlink()
    elif fault == "alias":
        alias = tmp_path / "alias.json"
        alias.symlink_to(path)
        path = alias
    control: Any = guard(30)
    if fault == "cancel":

        class Stop:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "material-input")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        control = Stop()
    if fault in {"none", "declarations"}:
        result = load_source_material(path, sha, expected, W, control)
        assert (
            result == material and result.site.token.owner == material.site.token.owner
        )
        assert path.read_bytes() == raw
    else:
        with pytest.raises(
            (ValueError, OSError, OperationStopped, EvidenceIntegrityError)
        ):
            load_source_material(path, sha, expected, W, control)


@pytest.mark.parametrize("site", ["admin", "map"])
@pytest.mark.parametrize("fault", ["none", "missing_sha", "sha_only", "hash"])
def test_actual_cli_passes_verified_body_and_requires_complete_pin_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, site: str, fault: str
) -> None:
    raw, material, runtime = original(site)
    path = tmp_path / "source.json"
    path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    calls = []
    module = admin if site == "admin" else maps

    def execute(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        assert kwargs["source_material"] == material
        return {}

    monkeypatch.setattr(
        module, "run_admin_navigation" if site == "admin" else "run", execute
    )
    argv = [
        "entry",
        material.browser.configuration.spec.scope.task.source_task_id,
        str(tmp_path / "deployment.json"),
        "--entry-budgets",
        str(runtime / "entry-budgets.json"),
        "--job-budgets",
        str(runtime / "job-budgets.json"),
        "--recovery-budgets",
        str(runtime / "source-recovery-budgets.json"),
    ]
    if fault != "sha_only":
        argv += ["--source-material", str(path)]
    if fault != "missing_sha":
        argv += ["--source-material-sha256", "0" * 64 if fault == "hash" else sha]
    monkeypatch.setattr(sys, "argv", argv)
    if fault == "none":
        module.main()
        assert len(calls) == 1
    else:
        with pytest.raises((SystemExit, ValueError, EvidenceIntegrityError)):
            module.main()
        assert calls == []


@pytest.mark.parametrize("fault", ["none", "task"])
def test_actual_admin_run_binds_material_into_supplier_without_a_source_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    _, material, runtime = original("admin")
    selected = selected_admin(
        material, None if fault == "none" else "196fe000070f772337aa"
    )
    events = []
    opaque = object()
    facts: dict[str, Any] = {}
    monkeypatch.setenv("LAB_JOB_OUTPUT_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(
        admin_inputs, "load_admin_navigation_group", lambda control: (selected,)
    )

    def deployment(*args: Any) -> object:
        events.append("deployment")
        return opaque

    monkeypatch.setattr(admin_deployment, "load_admin_deployment", deployment)

    @contextmanager
    def supplied(*args: Any, **kwargs: Any) -> Any:
        events.append("supply")
        assert kwargs["source_material"] == material
        try:
            yield SimpleNamespace(runtime=opaque, facts=facts)
        finally:
            events.append("close")

    monkeypatch.setattr(supply, "supply_admin_runtime", supplied)
    monkeypatch.setattr(
        admin,
        "execute_admin_navigation",
        lambda selection, current: {"material_consumption_join_only": True},
    )
    args: dict[str, Any] = dict(
        budgets=AdminProductionBudgets.model_validate_json(
            (runtime / "entry-budgets.json").read_bytes()
        ),
        job_budgets=OperationWindowBudgets.model_validate_json(
            (runtime / "job-budgets.json").read_bytes()
        ),
        recovery_budgets=SourceRecoveryBudgets.model_validate_json(
            (runtime / "source-recovery-budgets.json").read_bytes()
        ),
        origin=None,
        allowed_actions=("send_msg_to_user",),
        source_material=material,
    )
    if fault == "none":
        assert (
            admin.run_admin_navigation(
                selected.private.task.source_task_id,
                tmp_path / "deployment.json",
                **args,
            )
            == facts
        )
        assert events == ["deployment", "supply", "close"]
    else:
        with pytest.raises(OwnershipConflict):
            admin.run_admin_navigation(
                selected.private.task.source_task_id,
                tmp_path / "deployment.json",
                **args,
            )
        assert events == []


def test_original_admin_supplier_refuses_ended_source_owner_before_metadata_or_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, material, runtime = original("admin")
    selected = selected_admin(material)
    budgets = AdminProductionBudgets.model_validate_json(
        (runtime / "entry-budgets.json").read_bytes()
    )
    frozen, parameters = check_admin_deployment(retained(), budgets)
    frozen = replace(
        frozen,
        declaration=material.site.configuration.installation,
        actor=frozen.actor.model_copy(
            update={
                "release_ref": material.site.configuration.installation.manifest_ref
            }
        ),
    )
    deployment = AdminDeployment(
        frozen,
        parameters,
        tmp_path / "software.json",
        b"unit-only",
        tmp_path / "deployment.json",
    )
    execution, accounting = actual_slurm_execution()
    monkeypatch.setattr(
        supply, "original_execution", lambda control: (execution, accounting)
    )
    monkeypatch.setattr(supply, "PACKAGE", tmp_path)
    (tmp_path / "source-claims").mkdir()
    output = tmp_path / ("production-" + execution.job_id)
    output.mkdir()

    def forbidden(*a: Any, **kw: Any) -> Any:
        raise AssertionError("Ended source owner reached metadata/model")

    monkeypatch.setattr(supply, "owner_metadata_store", forbidden)
    monkeypatch.setattr(supply, "stage_admin_actor_artifact", forbidden)
    with pytest.raises(OwnershipConflict, match="another job owner"):
        with supply.supply_admin_runtime(
            selected,
            deployment,
            budgets,
            None,
            ("send_msg_to_user",),
            output,
            job_budgets=OperationWindowBudgets.model_validate_json(
                (runtime / "job-budgets.json").read_bytes()
            ),
            recovery_budgets=SourceRecoveryBudgets.model_validate_json(
                (runtime / "source-recovery-budgets.json").read_bytes()
            ),
            source_material=material,
        ):
            pytest.fail("Ended source supplied a live runtime")


def test_actual_map_entry_rejects_other_task_before_deployment_or_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, selected_material, runtime = original("map")
    other = decode_command(
        (
            W
            / "experiments/framework-map-navigation42-production-20261102-v1/production-4925677/source-read/last-request.json"
        ).read_bytes()
    ).material
    assert isinstance(other, ClosedMapReadMaterial)
    source_id = selected_material.browser.configuration.spec.scope.task.source_task_id
    assert other.browser.configuration.spec.scope.task.source_task_id != source_id
    monkeypatch.setenv("LAB_JOB_OUTPUT_DIRECTORY", str(tmp_path))
    # Selection-only premise avoids the already-consumed claim, never grants it.
    # The real original native/public binder still validates this exact member.
    monkeypatch.setattr(maps, "selected_navigation", map_inputs.declared_navigation)
    monkeypatch.setattr(
        map_deployment,
        "choose_deployment",
        lambda *a, **kw: SimpleNamespace(path=tmp_path / "must-not-be-read.json"),
    )
    with pytest.raises(ValueError, match="selected task/native"):
        maps.run(
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
            source_material=other,
        )
