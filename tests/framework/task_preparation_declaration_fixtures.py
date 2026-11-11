"""Shared original typed preparation declaration; explicit unit-only site reference."""

from datetime import datetime, timezone
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.reset import ResetPlan
from evidence_control_fixtures import EvidenceFixtureStore
from construction_storage_fixtures import put
from test_core_contracts import reference


def preparation_declaration(
    plan: TaskExecutionPlan,
    reset: ResetPlan,
    task: TaskBinding,
    store: EvidenceFixtureStore,
) -> SiteTaskPreparationPlan:
    op = plan.operation.model_copy(update={"allocation_id": "held-original-unit-site"})
    env = op.model_copy(
        update={
            "operation_id": "unit-env",
            "recovery_ref": reset.environment_recovery_ref,
        }
    )
    read = env.cleanup(
        "unit-resource-read", now=datetime.now(timezone.utc), seconds=30
    ).model_copy(update={"attempt_id": None})
    return SiteTaskPreparationPlan(
        scope=reset.scope,
        site_spec_ref=reference("private", "site-resource-spec/1"),
        task_binding_ref=put(store, task, "task-binding/1"),
        private_input_ref=task.private_spec_ref,
        snapshot_schema="unit-native-snapshot/1",
        snapshot_operation=op.model_copy(
            update={
                "operation_id": "unit-snapshot",
                "recovery_ref": reset.task_recovery_ref,
            }
        ),
        prepare_operation=op.model_copy(
            update={
                "operation_id": reset.parent_operation_id,
                "recovery_ref": reset.task_recovery_ref,
            }
        ),
        environment_operation=env,
        resource_read_operation=read,
    )
