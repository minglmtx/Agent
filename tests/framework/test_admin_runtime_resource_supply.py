"""Supply contract/failure tests, never real Admin source or Actor admission.

Only retained deployment declarations and current Slurm accounting/cgroup are
read. Metadata, staging and resource effects are explicitly replaced in failure
cases; they cannot count as actual runtime qualification or successful closure.
"""

import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
import admin_production_supply as supply
import admin_production_deployment as deployment_module
from admin_production_deployment import AdminDeployment, check_admin_deployment
from admin_production_task_plan import AdminProductionBudgets
from admin_production_inputs import load_admin_navigation_group
from lab_generate_skill.domain.admin_navigation_origin import AdminNavigationOrigin
from test_slurm_commands import guard
from test_linux_cgroups import actual_slurm_execution
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot

P = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-admin-navigation-production-20261102-v1"
)


def retained() -> dict[str, Any]:
    data = json.loads((P / "check-isolated-4902561/admin-deployment.json").read_bytes())
    assert isinstance(data, dict)
    return data


def test_original_declared_envelope_keeps_actor64_no_runtime_permission() -> None:
    frozen, parameters = check_admin_deployment(retained(), AdminProductionBudgets())
    assert parameters.max_input_tokens == 61440 and parameters.max_new_tokens == 4096
    assert frozen.engine_config.context_window == 65536
    assert frozen.preparation["source_or_resource_permission"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "paid",
        "claim",
        "source",
        "actor",
        "generation-bool",
        "training",
        "scope",
        "permission",
        "output",
        "engine",
    ],
)
def test_bad_complete_deployment_refuses_without_resource_effects(fault: str) -> None:
    data = copy.deepcopy(retained())
    if fault == "paid":
        data["paid_calls"] = 1
    elif fault == "claim":
        data["task_claim_created"] = True
    elif fault == "source":
        data["actual_source_members"] = ["old"]
    elif fault == "actor":
        data["actual_actor_members"] = ["old"]
    elif fault == "generation-bool":
        data["model_generations"] = False
    elif fault == "training":
        data["formal_training_qualification"] = True
    elif fault == "scope":
        data["preparation"]["site_scope"] = "map"
    elif fault == "permission":
        data["preparation"]["source_or_resource_permission"] = True
    elif fault == "output":
        data["parameters"]["max_new_tokens"] = 2048
    else:
        data["config"]["context_window"] = 131072
    with pytest.raises(ValueError):
        check_admin_deployment(data, AdminProductionBudgets())


@pytest.mark.parametrize("value", [None, [], "wrong", False])
def test_wrong_deployment_type_rejected(value: Any) -> None:
    with pytest.raises(TypeError):
        check_admin_deployment(value, AdminProductionBudgets())


def test_old_real_installation_cannot_bypass_new_outer_consumer_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Unit perimeter: do not claim that the old frozen code equals current A.
    # Exercise the real outer-manifest gate using its retained actual inputs.
    monkeypatch.setattr(deployment_module, "verify_source", lambda *a, **kw: None)
    monkeypatch.setattr(
        deployment_module, "admin_role_declaration", lambda frozen, software: frozen
    )
    path = P / "check-isolated-4902561/admin-deployment.json"
    with pytest.raises(ValueError, match="complete outer supplier"):
        deployment_module.load_admin_deployment(
            path, AdminProductionBudgets(), guard(30)
        )


@pytest.mark.parametrize("fault", ["initialize", "publication", "revoke"])
def test_partial_metadata_supply_retains_primary_and_revokes_without_site_or_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    data = retained()
    # This real short software allocation only reaches injected metadata
    # failures. It does not need or grant an hours-long source/Actor budget.
    budgets = AdminProductionBudgets(
        root_seconds=60, site_seconds=30, task_seconds=30, source_metadata_seconds=30
    )
    job_budgets = OperationWindowBudgets(
        execution_seconds=60,
        cleanup_seconds=180,
        final_margin_seconds=30,
        stop_signal_lead_seconds=210,
    )
    recovery_budgets = SourceRecoveryBudgets(
        preparation_metadata_seconds=1,
        browser_close_seconds=1,
        restore_seconds=1,
        resume_seconds=1,
        reset_facts_seconds=1,
        site_close_seconds=1,
    )
    frozen, parameters = check_admin_deployment(data, budgets)
    deployment = AdminDeployment(
        frozen,
        parameters,
        Path(data["software_path"]),
        b"explicit-unit-supply-only",
        P / "unit-deployment-not-a-grant.json",
    )
    selected = load_admin_navigation_group(guard(30))[0]
    execution, accounting = actual_slurm_execution()
    monkeypatch.setattr(
        supply, "original_execution", lambda control: (execution, accounting)
    )
    monkeypatch.setattr(supply, "PACKAGE", tmp_path)
    (tmp_path / "source-claims").mkdir()
    output = tmp_path / ("production-" + execution.job_id)
    output.mkdir()
    failure = OSError("original metadata supply failed")
    cleanup_error = RuntimeError("original metadata revoke failed")
    events = []

    class Store:
        last_exchange = None
        scope: Any = None

        def initialize(self, control: Any) -> EvidenceSessionSnapshot:
            events.append("initialize")
            if fault in ("initialize", "revoke"):
                raise failure
            return EvidenceSessionSnapshot(
                binding=self.scope.binding, capacity=self.scope.config.capacity
            )

        def put(self, *a: Any, **kw: Any) -> Any:
            events.append("publication")
            raise failure

    def revoke() -> None:
        events.append("revoke")
        if fault == "revoke":
            raise cleanup_error

    managed = SimpleNamespace(
        store=Store(), admission=SimpleNamespace(stop_new_io=revoke)
    )

    def supplied_store(scope: Any, *args: Any, **kwargs: Any) -> Any:
        managed.store.scope = scope
        return managed

    monkeypatch.setattr(supply, "owner_metadata_store", supplied_store)

    def forbidden(*a: Any, **kw: Any) -> Any:
        pytest.fail("failed metadata supply reached a resource effect")

    monkeypatch.setattr(supply, "stage_admin_actor_artifact", forbidden)
    # No real fixed proof can be used with the explicit synthetic store. It is
    # never read, dispatched or taken as a permission in these failure cases.
    monkeypatch.setattr(
        supply,
        "ClosedSourceReadTransport",
        lambda *a, **kw: SimpleNamespace(
            timings=[],
            quarantined=False,
            last_request=None,
            last_reply=None,
            last_capture=None,
        ),
    )
    origin = AdminNavigationOrigin(endpoint="http://127.0.0.1:18081/admin")
    expected = BaseExceptionGroup if fault == "revoke" else OSError
    with pytest.raises(expected) as error:
        with supply.supply_admin_runtime(
            selected,
            deployment,
            budgets,
            origin,
            ("send_msg_to_user",),
            output,
            job_budgets=job_budgets,
            recovery_budgets=recovery_budgets,
        ):
            pytest.fail("failed supplier returned a usable runtime")
    if fault == "revoke":
        assert isinstance(error.value, BaseExceptionGroup)
        assert error.value.exceptions == (failure, cleanup_error)
    else:
        assert error.value is failure
    assert events[-1] == "revoke"
    assert events == (
        ["initialize", "revoke"]
        if fault != "publication"
        else ["initialize", "publication", "revoke"]
    )
    facts = json.loads((output / "member-result.json").read_bytes())
    assert (
        facts["actual_actor_members_executed"] == []
        and facts["source_qualified"] is False
    )
    assert facts["metadata_admission_revoked"] is (fault != "revoke")
    assert not list((tmp_path / "source-claims").iterdir())


def test_partial_asset_stage_keeps_exact_original_root_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = retained()
    frozen, parameters = check_admin_deployment(data, AdminProductionBudgets())
    declared = AdminDeployment(
        frozen,
        parameters,
        Path(data["software_path"]),
        b"unit-stage-only",
        P / "unit-deployment-not-a-grant.json",
    )
    stage = tmp_path / "original-partial-stage"
    stage.mkdir()
    monkeypatch.setattr(tempfile, "mkdtemp", lambda **kw: str(stage))
    failure = OSError("original pinned model copy failed")
    calls = []

    def failed(*args: Any, **kwargs: Any) -> None:
        calls.append(args)
        raise failure

    monkeypatch.setattr(supply, "copy_pinned_file", failed)
    with pytest.raises(OSError) as error:
        supply.stage_admin_actor_artifact(declared, "unit-stage", guard(30))
    assert error.value is failure
    assert getattr(failure, "admin_staged_model_root") == str(stage)
    assert len(calls) == 1 and stage.is_dir()
