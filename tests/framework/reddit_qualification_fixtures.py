"""Real record/lifecycle primitives with explicit synthetic kernel/native authority."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import hashlib
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.site_worker import SiteWorkerReady
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteSlurmBinding,
    SiteResourceReady,
    SiteResourceStarted,
)
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    AllocationToken,
    ClosureReceipt,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeIntent
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.tasks.image_resume import ImageResume
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.bootstrap.reddit_image_records import (
    reddit_state_qualifications,
)
from reddit_preparation_fixtures import Case, prepared_case, put, metadata
from browser_step_fixtures import binding
from site_worker_fixtures import sources
from test_resource_journal import NoCancellation
from test_slurm_commands import guard


class Authority:
    calls = 0
    denied = False

    def verify(
        self,
        scope: StateScope,
        selection_ref: EvidenceRef,
        phase: Literal["environment", "reset"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if self.denied:
            raise PermissionError("synthetic qualification denied")


@dataclass
class QualifiedCase:
    preparation: Case
    environment: EnvironmentSelection
    environment_ref: EvidenceRef
    site: SiteResourceSpec
    started: SiteResourceStarted
    authority: Authority


@contextmanager
def qualified(root: Path, node: Path) -> Iterator[QualifiedCase]:
    identities = tuple(
        ProcessIdentity(node_id="node", boot_id="boot", process_id=n, start_ticks=1)
        for n in (10, 11, 12)
    )
    native_guard = ProcessOwnerGuard(
        controller=identities[0], supervisor=identities[1], worker=identities[2]
    )
    with prepared_case(
        root,
        node,
        owner_guard=native_guard,
    ) as p:
        config, store = p.configuration, p.store
        b = binding(config.token.owner.job_id, real=False)
        parent = b.parent.model_copy(update={"writer": native_guard.controller})
        slurm = SiteSlurmBinding.model_validate(
            {
                **b.model_dump(),
                "parent": parent,
                "schema_version": "site-slurm-binding/1",
            }
        )
        site = SiteResourceSpec(configuration=config, slurm=slurm)
        member = parent.model_copy(
            update={
                "writer": native_guard.worker,
                "step_id": "0",
                "user_path": parent.user_path.replace("step_batch", "step_0"),
                "user_inode": parent.user_inode + 100,
                "task_inode": parent.task_inode + 100,
            }
        )
        target = SlurmStepTarget(
            execution=slurm.execution,
            step_name="synthetic-site",
            resources="cpu_only",
            launcher=native_guard.controller,
            worker=member,
        )
        proof = store.put(
            b'{"explicitly_synthetic":true}', metadata("site-step-raw/1"), guard()
        )
        ready = SiteResourceReady(
            worker=SiteWorkerReady(
                owner_guard=native_guard,
                installed_sources=sources(config.installation, guard()),
            ),
            controller=SlurmControllerStep(
                target=target,
                started_at_epoch=slurm.execution.started_at_epoch + 1,
                gpu_type=None,
                memory="1G",
            ),
            evidence=proof,
        )
        started = SiteResourceStarted(
            ready=ready,
            instance=p.native.artifacts.context.instance,
            evidence=store.put(
                b'{"explicitly_synthetic":true}',
                metadata("site-resource-fact/1"),
                guard(),
            ),
        )
        assert p.inputs.request.snapshot_ref is not None
        environment = EnvironmentSelection(
            scope=p.inputs.environment.scope,
            spec_ref=p.inputs.binding.baseline_ref,
            site_spec_ref=put(store, site),
            site_started_ref=put(store, started),
            snapshot_ref=p.inputs.request.snapshot_ref,
        )
        ref = put(store, environment)
        authority = Authority()
        records = reddit_state_qualifications(
            store, OperationGuards(SystemClock(), NoCancellation()), authority
        )
        operation = p.inputs.environment.operation
        published = records.publish_environment(ref, operation)
        baseline = records.load_environment(ref, published, operation)
        selection = p.inputs.selection.model_copy(update={"environment_ref": published})
        p.inputs = p.inputs.model_copy(
            update={"environment": baseline, "selection": selection}
        )
        yield QualifiedCase(p, environment, ref, site, started, authority)


def restore(
    c: QualifiedCase,
    tokens: tuple[AllocationToken, ...],
    closure_refs: tuple[EvidenceRef, ...],
) -> ResetSelection:
    p = c.preparation
    request = p.native.next("restore", "original-restore")
    result = p.native.task.execute_task(request, control=guard())
    result_ref = put(p.store, result)
    resume = SiteResumeRequest(
        restore_request=request,
        restore_result_ref=result_ref,
        operation=request.operation.cleanup(
            "original-resume", now=datetime.now(timezone.utc), seconds=30
        ).model_copy(update={"recovery_ref": c.site.token.recovery_ref}),
    )
    intent = SiteResumeIntent(
        configuration_sha256=hashlib.sha256(
            c.site.configuration.model_dump_json().encode()
        ).hexdigest(),
        request=resume,
    )
    resumed = ImageResume(p.native.task).resume_frontend(resume, control=guard())
    assert request.operation.recovery_ref is not None
    plan = ResetPlan(
        scope=c.environment.scope,
        parent_operation_id=p.inputs.request.operation.operation_id,
        spec_ref=c.environment.spec_ref,
        task_recovery_ref=request.operation.recovery_ref,
        environment_recovery_ref=c.site.token.recovery_ref,
        attempt_allocations=tokens,
    )
    return ResetSelection(
        environment_selection_ref=c.environment_ref,
        plan_ref=put(p.store, plan),
        restore_request_ref=put(p.store, request),
        restore_result_ref=result_ref,
        resume_request_ref=put(p.store, resume),
        resume_result_ref=put(p.store, resumed),
        resume_intent_ref=put(p.store, intent),
        closure_refs=closure_refs,
    )
