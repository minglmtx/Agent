"""Real native snapshot shapes over coherent synthetic Shopping effects/rights."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.sites.shopping.tasks.navigation_admission import task_input
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from lab_generate_skill.sites.shopping.worker_instance import ShoppingWorkerInstance
from shopping_category_native_fixtures import worker, request
from shopping_task_fixtures import QueryCommands
from site_worker_fixtures import configuration
from test_shopping_order_eta_inputs import reference
from test_slurm_commands import guard


@dataclass
class NativeRequestCase:
    worker: ShoppingWorkerInstance
    commands: QueryCommands
    configuration: SiteWorkerConfiguration
    first: SiteTaskRequest
    binding: TaskBinding
    recovery: RecoveryPlan
    environment: RecoveryPlan


def request_case(root: Path, raw: bytes, public: PublicTask) -> NativeRequestCase:
    w, commands = worker(root)
    first = request(raw, public)
    base = configuration()
    files = w.instance.files_plan
    config = SiteWorkerConfiguration.model_validate(
        base.model_copy(
            update={
                "site_id": "shopping",
                "files": files,
                "token": base.token.model_copy(
                    update={"expected_resource_id": files.instance_id}
                ),
            }
        )
    )
    policy = category_navigation_initial_spec(first.task)
    baseline = reference(
        policy.model_dump_json().encode(), content_schema=policy.schema_version
    )
    recovery = RecoveryPlan(
        recovery_id="category-task",
        owner=config.token.owner,
        attempt_id=first.operation.attempt_id,
        baseline_ref=baseline,
        restore_component_id="shopping-category-navigation",
        restore_component_version="1",
        state_coverage=policy.task_reset_checks,
    )
    environment = RecoveryPlan(
        recovery_id="category-environment",
        owner=config.token.owner,
        baseline_ref=baseline,
        restore_component_id="shopping-services",
        restore_component_version="1",
        state_coverage=policy.environment_reset_checks,
    )
    config = config.model_copy(
        update={
            "token": config.token.model_copy(
                update={
                    "recovery_ref": reference(
                        environment.model_dump_json().encode(),
                        content_schema=environment.schema_version,
                    )
                }
            )
        }
    )
    spec = task_input(first).spec
    binding = TaskBinding(
        identity=first.task,
        registration_id="original-category-unit-binding",
        public_task_ref=reference(
            public.model_dump_json().encode(), content_schema=public.schema_version
        ).model_copy(update={"visibility": "public"}),
        private_spec_ref=reference(
            spec.model_dump_json().encode(), content_schema=spec.schema_version
        ),
        baseline_ref=baseline,
    )
    first = first.model_copy(
        update={
            "binding_ref": reference(
                binding.model_dump_json().encode(),
                content_schema=binding.schema_version,
            ),
            "operation": first.operation.model_copy(
                update={
                    "recovery_ref": reference(
                        recovery.model_dump_json().encode(),
                        content_schema=recovery.schema_version,
                    )
                }
            ),
        }
    )
    return NativeRequestCase(w, commands, config, first, binding, recovery, environment)


def saved(case: NativeRequestCase) -> tuple[SiteTaskRequest, bytes]:
    result = case.worker.execute_task(case.first, control=guard(60))
    raw = result.private_result.encode()
    return (
        case.first.model_copy(
            update={
                "action": "prepare",
                "operation": case.first.operation.model_copy(
                    update={"operation_id": "category-prepare"}
                ),
                "snapshot_ref": reference(
                    raw, content_schema="shopping-category-recovery/1"
                ),
            }
        ),
        raw,
    )
