"""Admin source-dependent declarations on original unit source/claim receipts.

No source/model/resource permission is created by these configuration tests.
Original source fixtures explicitly simulate native/kernel/page premises.
"""

from dataclasses import replace
import json
from pathlib import Path
from typing import Any
import pytest
from admin_production_task_plan import (
    AdminProductionBudgets,
    prepare_admin_execution_configuration,
    execution_declarations,
    freeze_admin_execution_inputs,
)
from production_inputs import OriginalDocuments
from lab_generate_skill.adapters.sites.resource_records import (
    reference as site_resource_reference,
)
from production_task_plan import FrozenExecutionInputs
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.run_plan import RunPlan, ExecutionWorkload
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from admin_navigation_owned_fixtures import owned_navigation_case
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path


def frozen_case(c: Any) -> FrozenExecutionInputs:
    store, controls = c.source.site.evidence, c.source.site.controls
    op = c.declarations.plan.read_operation
    reads, control = StateReads(store), controls.bind(op)
    binding = c.admitted.published.source.run
    run = reads.parse(binding.plan_ref, "run-plan/3", RunPlan, control)
    assert isinstance(run.workload, ExecutionWorkload)
    policy = reads.parse(
        run.workload.execution_policy_ref,
        "engineering-execution-policy/3",
        EngineeringActorPolicy,
        control,
    )
    context = reads.parse(
        policy.actor_context_ref,
        "actor-context-configuration/1",
        ActorContextConfiguration,
        control,
    )
    inputs = reads.parse(
        run.workload.task_inputs_ref,
        "execution-task-inputs/1",
        ExecutionTaskInputs,
        control,
    )
    return FrozenExecutionInputs(
        run,
        binding,
        context,
        policy.actor_context_ref,
        policy,
        run.models[0].parameters_ref,
        c.declarations.plan.skill_ref,
        inputs.task_binding_ref,
        run.tasks[0],
        inputs,
    )


def test_admin_preclaim_configuration_and_original_late_source_binder(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
) -> None:
    # This source helper requires an existing root; its temp claims stay local.
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, contracts)
    frozen = frozen_case(c)
    site = c.owned.resources.site.spec
    scope = c.declarations.preparation.scope
    root = c.source.site
    operation = c.declarations.plan.read_operation.model_copy(
        update={"operation_id": "unit-admin-configuration"}
    )
    acquisition = root.op.model_copy(
        update={
            "operation_id": "unit-admin-configuration-acquire",
            "allocation_id": site.token.allocation_id,
            "recovery_ref": site.token.recovery_ref,
        }
    )
    before = {
        f.name: f.read_bytes() for f in root.journal._root.glob("*.resource.json")
    }
    budgets = AdminProductionBudgets(task_seconds=180, metadata_cleanup_seconds=60)
    prepared = prepare_admin_execution_configuration(
        frozen,
        site,
        acquisition,
        scope,
        OriginalDocuments(root.evidence, root.controls),
        operation,
        budgets,
        root.clock,
    )
    assert prepared.preparation.site_spec_ref == site_resource_reference(
        site.model_dump_json().encode(), site.schema_version
    )
    assert prepared.preparation.site_spec_ref.producer == "fixed-site-resource"
    declared = execution_declarations(prepared, c.admitted.published)
    assert declared.preparation.snapshot_schema == "admin-navigation-recovery/1"
    assert declared.capture.page_collector_id == "admin-navigation-page"
    assert declared.capture.guard_collector_id == "admin-navigation-snapshot-integrity"
    assert declared.capture.schema_version == "task-capture-plan/2"
    assert declared.capture.metadata_close_seconds == 60
    assert declared.capture.close_seconds == 60
    assert declared.plan.cleanup_seconds == 60
    assert declared.plan.intent == c.admitted.published.source.intent
    assert declared.plan.source_ref == c.admitted.published.source_ref
    assert declared.plan.evaluation.identity == scope.task
    assert declared.reset.scope == scope
    assert prepared.frozen == frozen
    assert before == {
        f.name: f.read_bytes() for f in root.journal._root.glob("*.resource.json")
    }
    foreign = replace(
        prepared,
        frozen=replace(
            frozen,
            inputs=frozen.inputs.model_copy(
                update={
                    "source_context_receipt_ref": frozen.inputs.source_context_receipt_ref.model_copy(
                        update={"producer": "foreign-source"}
                    )
                }
            ),
        ),
    )
    with pytest.raises(ValueError, match="Actual admitted source changed"):
        execution_declarations(foreign, c.admitted.published)


@pytest.mark.parametrize(
    "changes",
    [
        {"root_seconds": True},
        {"root_seconds": "21600"},
        {"root_seconds": 21599},
        {"source_metadata_seconds": 3601},
        {"metadata_cleanup_seconds": 59},
        {"native_close_seconds": 61},
        {"storage_cleanup_seconds": 29},
        {"generation_seconds": 601},
        {"interaction_seconds": 181},
        {"extra": 1},
    ],
)
def test_admin_illegal_complete_budget_configuration_before_resource_effects(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        AdminProductionBudgets.model_validate(changes)


def test_admin_deployment_uses_actual_prepared_actor64_and_release() -> None:
    from lab_generate_skill.domain.actor_engine import (
        ActorEngineConfig,
        LocalActorParameters,
    )
    from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
    from lab_generate_skill.domain.release_installation import ReleaseInstallation

    path = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-admin-navigation-production-20261102-v1/check-isolated-4902561/admin-deployment.json"
    )
    value = json.loads(path.read_text())
    AdminProductionBudgets().check_deployment(
        ReleaseInstallation.model_validate_json(json.dumps(value["installation"])),
        ActorModelBinding.model_validate_json(json.dumps(value["actor"])),
        ActorEngineConfig.model_validate_json(json.dumps(value["config"])),
        LocalActorParameters.model_validate_json(json.dumps(value["parameters"])),
    )
