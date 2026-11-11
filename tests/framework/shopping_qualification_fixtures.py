"""Actual CAS/qualification adapters; synthetic native workers and source rights."""

from collections.abc import Iterator, Callable
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.bootstrap.shopping_state_qualification import (
    shopping_state_qualifications,
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
)
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeIntent
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.tasks.order_eta_policy import (
    order_eta_initial_spec,
    ENVIRONMENT_RESET_CHECKS,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_recovery import (
    OrderEtaRecoverySnapshot,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_resume import OrderEtaResume
from shopping_task_fixtures import case, request
from shopping_services_fixtures import Group
from site_resource_fixtures import resource_case
from site_worker_fixtures import configuration
from preparation_record_fixtures import put
from state_qualification_fixtures import Authority
from test_slurm_commands import guard
from lab_generate_skill.sites.shopping.tasks.navigation_lifecycle import (
    CategoryNavigationLifecycle,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_lifecycle import (
    OrderEtaLifecycle,
)
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_recovery import (
    CategoryNavigationRecoverySnapshot,
)
from lab_generate_skill.sites.shopping.tasks.navigation_resume import (
    CategoryNavigationResume,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
)
from lab_generate_skill.bootstrap.shopping_category_records import (
    category_state_qualifications,
)
from lab_generate_skill.sites.shopping.tasks.state_codec import (
    ShoppingTaskStateCodec,
    Private,
)
from urllib.parse import urlsplit


@contextmanager
def qualified(
    root: Path,
    node: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    before_reset: Callable[[dict[str, Any]], ClosureReceipt | None] | None = None,
    category: tuple[bytes, PublicTask] | None = None,
    prepare_with: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    config = configuration(job_id="4752096")
    # Normalize synthetic service identities to the actual fixture controller's
    # host/boot. These remain explicit fake processes, never kernel proof.
    from lab_generate_skill.adapters.processes.worker_identity import (
        current_process_identity,
    )

    host = current_process_identity()
    pin = Group.pin_namespace

    def original_host(
        group: Group, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        fact = pin(group, name, control)
        fact = fact.model_copy(
            update={
                "launcher": fact.launcher.model_copy(
                    update={
                        "node_id": host.node_id,
                        "boot_id": host.boot_id,
                        "start_ticks": host.start_ticks + 10 + group.generation,
                    }
                ),
                "init": fact.init.model_copy(
                    update={
                        "node_id": host.node_id,
                        "boot_id": host.boot_id,
                        "start_ticks": host.start_ticks + 20 + group.generation,
                    }
                ),
            }
        )
        group.pins[-1] = fact
        return fact

    monkeypatch.setattr(Group, "pin_namespace", original_host)
    eta_worker, commands, groups = case(node)
    worker: OrderEtaLifecycle | CategoryNavigationLifecycle = (
        CategoryNavigationLifecycle(eta_worker.instance)
        if category is not None
        else eta_worker
    )
    files = worker.instance.files_plan
    config = config.model_copy(
        update={
            "site_id": "shopping",
            "files": files,
            "token": config.token.model_copy(
                update={"expected_resource_id": files.instance_id}
            ),
        }
    )
    c = resource_case(root, monkeypatch, config=config)
    store = c.evidence
    template = request()
    if category is not None:
        template = template.model_copy(update={"task": category[1].identity})
    codec = ShoppingTaskStateCodec(
        template.task,
        "page_navigation" if category is not None else "recorded_order_eta",
    )
    spec = codec.policy
    spec_ref = put(store, spec)
    env_recovery = RecoveryPlan(
        recovery_id="shopping-environment",
        owner=c.spec.token.owner,
        baseline_ref=spec_ref,
        restore_component_id="shopping-services",
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
        recovery_id="shopping-task",
        owner=scope.owner,
        attempt_id=scope.attempt_id,
        baseline_ref=spec_ref,
        restore_component_id=codec.recovery_component,
        restore_component_version="1",
        state_coverage=spec.task_reset_checks,
    )
    task_recovery_ref = put(store, task_recovery)
    from test_shopping_order_eta_inputs import public_task, FIXTURE
    from lab_generate_skill.domain.evidence import EvidenceMetadata
    from lab_generate_skill.bootstrap.shopping_order_eta import load_order_eta_inputs
    from lab_generate_skill.sites.shopping.tasks.order_eta_state import (
        OrderEtaExecutionInput,
    )

    public = (
        public_task(start_url="http://127.0.0.1:12001/customer/account/")
        if category is None
        else category[1].model_copy(
            update={
                "start_url": urlsplit(category[1].start_url)
                ._replace(netloc="127.0.0.1:12001")
                .geturl()
            }
        )
    )
    raw = FIXTURE.read_bytes() if category is None else category[0]
    native_ref = store.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="shopping-native-contract/1",
            visibility="private",
            producer="unit",
        ),
        control=guard(),
    )
    if category is None:
        eta_private = load_order_eta_inputs(raw, native_ref, public).private_spec
        private: Private = eta_private
        envelope = OrderEtaExecutionInput(spec=eta_private).model_dump_json()
    else:
        category_private = load_category_navigation_inputs(
            raw, native_ref, public
        ).private_spec
        private = category_private
        envelope = CategoryNavigationExecutionInput(
            spec=category_private
        ).model_dump_json()
    template = template.model_copy(update={"private_input": envelope})
    binding = TaskBinding(
        identity=template.task,
        registration_id="unit-shopping",
        public_task_ref=put(store, public, visibility="public"),
        private_spec_ref=put(store, private),
        baseline_ref=spec_ref,
    )
    binding_ref = put(store, binding)
    template = template.model_copy(
        update={
            "binding_ref": binding_ref,
            "operation": template.operation.model_copy(
                update={"recovery_ref": task_recovery_ref}
            ),
        }
    )
    browser_recovery = RecoveryPlan(
        recovery_id="shopping-browser",
        owner=scope.owner,
        attempt_id=scope.attempt_id,
        baseline_ref=spec_ref,
        restore_component_id="browser-close",
        restore_component_version="1",
        state_coverage=("browser-processes",),
    )
    browser = AllocationToken(
        allocation_id="browser",
        owner=scope.owner,
        scope="attempt",
        attempt_id=scope.attempt_id,
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
        produced = (
            None
            if prepare_with is None
            else prepare_with(
                dict(
                    c=c,
                    store=store,
                    worker=worker,
                    live=live,
                    spec=spec,
                    spec_ref=spec_ref,
                    scope=scope,
                    public=public,
                    binding=binding,
                    template=template,
                    plan=plan,
                    plan_ref=plan_ref,
                )
            )
        )
        result = (
            worker.execute_task(
                template, control=guard(60) if category is not None else guard()
            )
            if produced is None
            else produced["snapshot_result"]
        )
        snapshot = codec.snapshot_type.model_validate_json(result.private_result)
        snapshot_ref = put(store, snapshot)
        env = EnvironmentSelection(
            scope=scope,
            spec_ref=spec_ref,
            site_spec_ref=put(store, c.spec),
            site_started_ref=put(store, live.site),
            snapshot_ref=snapshot_ref,
        )
        env_ref = (
            put(store, env)
            if produced is None
            else produced["environment_selection_ref"]
        )
        op = template.operation.model_copy(
            update={"operation_id": "environment", "recovery_ref": env_recovery_ref}
        )
        authority = Authority()
        records = (
            category_state_qualifications(store, c.controls, authority)
            if category is not None
            else shopping_state_qualifications(store, c.controls, authority)
        )
        environment_ref = (
            records.publish_environment(env_ref, op)
            if produced is None
            else produced["environment_ref"]
        )
        prepare = template.model_copy(
            update={
                "action": "prepare",
                "snapshot_ref": snapshot_ref,
                "operation": template.operation.model_copy(
                    update={"operation_id": "prepare"}
                ),
            }
        )
        if produced is None:
            preparation = worker.execute_task(prepare, control=guard())
        else:
            prepare, preparation = (
                produced["prepare_request"],
                produced["prepare_result"],
            )
        original_closure = (
            before_reset(
                dict(
                    c=c,
                    store=store,
                    worker=worker,
                    live=live,
                    spec=spec,
                    spec_ref=spec_ref,
                    scope=scope,
                    public=public,
                    binding=binding,
                    prepare=prepare,
                    preparation=preparation,
                    snapshot_result=result,
                    recorded_preparation=produced,
                    environment_ref=environment_ref,
                    environment_selection_ref=env_ref,
                    browser=browser,
                    plan=plan,
                    plan_ref=plan_ref,
                )
            )
            if before_reset
            else None
        )
        closure = original_closure or ClosureReceipt(
            token=browser,
            operation_id="browser-close",
            status="closed",
            evidence=(plan_ref,),
        )
        assert closure.token == browser and closure.status == "closed"
        closure_ref = put(store, closure)
        restore = prepare.model_copy(
            update={
                "action": "restore",
                "operation": prepare.operation.cleanup(
                    "restore", now=datetime.now(timezone.utc), seconds=30
                ),
            }
        )
        restored = worker.execute_task(restore, control=guard())
        restored_ref = put(store, restored)
        resume = SiteResumeRequest(
            restore_request=restore,
            restore_result_ref=restored_ref,
            operation=restore.operation.cleanup(
                "resume", now=datetime.now(timezone.utc), seconds=30
            ).model_copy(update={"recovery_ref": env_recovery_ref}),
        )
        resumed = (
            CategoryNavigationResume(worker).resume_frontend(resume, control=guard())
            if isinstance(worker, CategoryNavigationLifecycle)
            else OrderEtaResume(worker).resume_frontend(resume, control=guard())
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
            restore_result_ref=restored_ref,
            resume_request_ref=put(store, resume),
            resume_result_ref=put(store, resumed),
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
            worker=worker,
            records=records,
            checks=records.checks,
            authority=authority,
            environment=env,
            selection_ref=env_ref,
            environment_ref=environment_ref,
            operation=op,
            reset=reset,
            reset_ref=reset_ref,
            reset_op=reset_op,
            snapshot=snapshot,
            prepare=prepare,
            preparation=preparation,
            binding=binding,
            public=public,
            spec=spec,
            scope=scope,
            plan=plan,
        )
