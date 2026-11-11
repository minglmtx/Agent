"""Synthetic native measurements and resource identities; actual CAS and tree I/O."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal
import hashlib
import pytest
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.bootstrap.admin_state_qualification import (
    admin_state_qualifications,
)
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.lifecycle import (
    RecoveryPlan,
    AllocationToken,
    ClosureReceipt,
    OperationContext,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_resume import (
    SiteResumeRequest,
    SiteResumeResult,
    SiteResumeIntent,
)
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.tasks.product_state_policy import (
    product_initial_state_spec,
    ENVIRONMENT_RESET_CHECKS,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_lifecycle import (
    AdminProductLifecycle,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_recovery_contract import (
    ProductRestored,
)
from lab_generate_skill.sites.shopping_admin.service_contract import (
    AdminServiceSpec,
    AdminPorts,
)
from lab_generate_skill.sites.shopping_admin.instance_contract import AdminInstancePlan
from lab_generate_skill.sites.shopping_admin.frontend_recovery_contract import (
    AdminFrontendRecovered,
)
from site_resource_fixtures import resource_case
from site_worker_fixtures import configuration
from test_site_task_execution import request
from test_product_recovery_rpc import Commands
from preparation_record_fixtures import put
from frontend_fixtures import frontend
from frontend_recovery_fixtures import recovered_namespace
from test_slurm_commands import guard


class Authority:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.denied = False

    def verify(
        self,
        scope: StateScope,
        selection_ref: EvidenceRef,
        phase: Literal["environment", "reset"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls.append(phase)
        if self.denied:
            raise PermissionError("synthetic qualification denied")


@contextmanager
def qualified(root: Path, node: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    config = configuration(job_id="4752096")
    config = config.model_copy(
        update={"files": config.files.model_copy(update={"node_root": str(node)})}
    )
    c = resource_case(root, monkeypatch, config=config)
    store = c.evidence
    template = request("snapshot", "snapshot")
    spec = product_initial_state_spec(template.task)
    spec_ref = put(store, spec)
    env_recovery = RecoveryPlan(
        recovery_id="environment",
        owner=c.spec.token.owner,
        baseline_ref=spec_ref,
        restore_component_id="admin-frontend",
        restore_component_version="1",
        state_coverage=ENVIRONMENT_RESET_CHECKS,
    )
    env_recovery_ref = put(store, env_recovery)
    c.spec = c.spec.model_copy(
        update={
            "configuration": c.spec.configuration.model_copy(
                update={
                    "token": c.spec.token.model_copy(
                        update={"recovery_ref": env_recovery_ref}
                    )
                }
            )
        }
    )
    c.op = c.op.model_copy(update={"recovery_ref": env_recovery_ref})
    scope = StateScope(
        owner=c.spec.token.owner,
        task=template.task,
        attempt_id="attempt",
        context_id="context",
    )
    task_recovery = RecoveryPlan(
        recovery_id="task",
        owner=scope.owner,
        attempt_id=scope.attempt_id,
        baseline_ref=spec_ref,
        restore_component_id="admin-product",
        restore_component_version="3",
        state_coverage=spec.task_reset_checks,
    )
    task_recovery_ref = put(store, task_recovery)
    binding = TaskBinding(
        identity=template.task,
        registration_id="unit",
        public_task_ref=template.binding_ref.model_copy(
            update={"content_schema": "public-task/1", "visibility": "public"}
        ),
        private_spec_ref=template.binding_ref,
        baseline_ref=spec_ref,
    )
    template = template.model_copy(
        update={
            "binding_ref": put(store, binding),
            "operation": template.operation.model_copy(
                update={"recovery_ref": task_recovery_ref}
            ),
        }
    )
    browser_recovery = task_recovery.model_copy(
        update={
            "recovery_id": "browser",
            "restore_component_id": "browser-close",
            "restore_component_version": "1",
            "state_coverage": ("browser-processes",),
        }
    )
    browser = AllocationToken(
        allocation_id="browser",
        owner=scope.owner,
        scope="attempt",
        attempt_id="attempt",
        resource_kind="browser",
        expected_resource_id="browser-instance",
        provider_id="fixed-browser-worker",
        provider_version="3",
        recovery_ref=put(store, browser_recovery),
    )
    plan = ResetPlan(
        scope=scope,
        parent_operation_id="prepare",
        spec_ref=spec_ref,
        task_recovery_ref=task_recovery_ref,
        environment_recovery_ref=env_recovery_ref,
        attempt_allocations=(browser,),
    )
    plan_ref = put(store, plan)
    with registered_site(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=store,
        controls=c.controls,
        clock=c.clock,
        authority=c.authority,
    ) as live:
        service = AdminServiceSpec(
            layout=AdminInstancePlan(
                files=config.files, apptainer=config.apptainer
            ).layout,
            ports=AdminPorts(
                web=12001, database=12002, redis=12003, search=12004, transport=12005
            ),
        )
        (node / "state/app/var/training-mail").mkdir(parents=True)
        worker = AdminProductLifecycle(
            service, Commands(), lambda control: frontend(service)
        )
        saved = worker.execute_task(template, control=guard())
        from lab_generate_skill.sites.shopping_admin.tasks.product_recovery_contract import (
            ProductRecoverySnapshot,
        )

        snapshot = ProductRecoverySnapshot.model_validate_json(saved.private_result)
        snapshot_ref = put(store, snapshot)
        env = EnvironmentSelection(
            scope=scope,
            spec_ref=spec_ref,
            site_spec_ref=put(store, c.spec),
            site_started_ref=put(store, live.site),
            snapshot_ref=snapshot_ref,
        )
        env_ref = put(store, env)
        op = template.operation.model_copy(
            update={"operation_id": "environment", "recovery_ref": env_recovery_ref}
        )
        authority = Authority()
        records = admin_state_qualifications(store, c.controls, authority)
        environment_ref = records.publish_environment(env_ref, op)
        prepare = template.model_copy(
            update={
                "action": "prepare",
                "snapshot_ref": snapshot_ref,
                "operation": template.operation.model_copy(
                    update={"operation_id": "prepare"}
                ),
            }
        )
        worker.execute_task(prepare, control=guard())
        closure = ClosureReceipt(
            token=browser,
            operation_id="browser-close",
            status="closed",
            evidence=(plan_ref,),
        )
        closure_ref = put(store, closure)
        restore = prepare.model_copy(
            update={
                "action": "restore",
                "operation": prepare.operation.cleanup(
                    "restore", now=datetime.now(timezone.utc), seconds=30
                ),
            }
        )
        restored_result = worker.execute_task(restore, control=guard())
        restored = ProductRestored.model_validate_json(restored_result.private_result)
        restored_result_ref = put(store, restored_result)
        resume = SiteResumeRequest(
            restore_request=restore,
            restore_result_ref=restored_result_ref,
            operation=restore.operation.cleanup(
                "resume", now=datetime.now(timezone.utc), seconds=30
            ).model_copy(update={"recovery_ref": env_recovery_ref}),
        )
        resumed = AdminFrontendRecovered(
            stopped=restored.frontend,
            state_restored_sha256=hashlib.sha256(
                restored.state.model_dump_json().encode()
            ).hexdigest(),
            before_start=restored.frontend.backend,
            namespaces=(
                recovered_namespace("nginx-restored"),
                recovered_namespace("php-restored"),
            ),
            backend_ready=True,
            frontend_ready=True,
        )
        result = SiteResumeResult(
            request_sha256=resume.digest, private_result=resumed.model_dump_json()
        )
        intent = SiteResumeIntent(
            configuration_sha256=hashlib.sha256(
                c.spec.configuration.model_dump_json().encode()
            ).hexdigest(),
            request=resume,
        )
        reset = ResetSelection(
            environment_selection_ref=env_ref,
            plan_ref=plan_ref,
            restore_request_ref=put(store, restore),
            restore_result_ref=restored_result_ref,
            resume_request_ref=put(store, resume),
            resume_result_ref=put(store, result),
            resume_intent_ref=put(store, intent),
            closure_refs=(closure_ref,),
        )
        reset_ref = put(store, reset)
        reset_op = prepare.operation.cleanup(
            "reset-summary", now=datetime.now(timezone.utc), seconds=30
        ).model_copy(update={"recovery_ref": env_recovery_ref})
        yield dict(
            c=c,
            store=store,
            records=records,
            authority=authority,
            environment=env,
            environment_ref=environment_ref,
            selection_ref=env_ref,
            operation=op,
            reset=reset,
            reset_ref=reset_ref,
            reset_op=reset_op,
            snapshot=snapshot,
            restored=restored,
            resume=resume,
            resumed=resumed,
        )
