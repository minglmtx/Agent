"""Original physical task resources over the existing retained site/browser/model.

No lifecycle, dispatch or restore is implemented here. Phase admission remains
in the existing application adapters. Each resource check reads its original
journal and actual worker incarnation; cleanup has an independent bounded read.
"""

import json
from datetime import datetime, timezone
from uuid import uuid4
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.task_owner import OriginalTaskBrowserOwner
from lab_generate_skill.adapters.browsergym.retained_closure import (
    original_closed_browser,
)
from lab_generate_skill.adapters.browsergym.resource_records import phase
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.lifecycle import (
    OperationContext,
    ResourceRecord,
    ClosureReceipt,
)
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.task_finalization import UnstartedTaskBrowser
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes


class OriginalTaskResourceOwner:
    def __init__(
        self,
        owner: ClaimedRunResourceOwner,
        plan: TaskExecutionPlan,
        site: RetainedSiteResource,
        browser: OriginalTaskBrowserOwner,
        model: ActorExecutionScope,
        *,
        inputs: TaskInitializationInputs | None = None,
    ) -> None:
        if (
            not isinstance(owner, ClaimedRunResourceOwner)
            or not isinstance(site, RetainedSiteResource)
            or not isinstance(model, ActorExecutionScope)
            or not isinstance(browser, OriginalTaskBrowserOwner)
        ):
            raise TypeError(
                "Original actual retained site/browser/model owner required"
            )
        self.owner, self.plan, self.site, self.browser_owner, self.model = (
            owner,
            TaskExecutionPlan.model_validate(plan),
            site,
            browser,
            model,
        )
        self.browser = browser.original
        self.inputs = inputs
        if inputs is not None and inputs.plan != self.plan:
            raise OwnershipConflict("Resource bodies changed original task scope")
        if (
            self.plan != owner.task_plan
            or site.spec.token.owner != owner.run.owner
            or model.binding.resource.owner != owner.run.owner
            or browser.token.owner != owner.run.owner
            or browser.token.attempt_id != self.plan.intent.binding.attempt_id
        ):
            raise OwnershipConflict("Task resources changed original claimed run")

    def bounded_read(self, control: OperationControl) -> OperationContext:
        seconds = min(float(self.plan.cleanup_seconds), control.checkpoint())
        return self.plan.read_operation.cleanup(
            "task-resource-read-" + uuid4().hex,
            now=datetime.now(timezone.utc),
            seconds=seconds,
        )

    def require(
        self, operation: OperationContext, control: OperationControl, *, live: bool
    ) -> RunPlan:
        plan = self.owner.require(operation, control, new_work=live)
        # This is the original model allocation, not a synthesized Actor scope.
        token = self.model.spec.token
        model_op = operation.model_copy(
            update={
                "allocation_id": token.allocation_id,
                "recovery_ref": token.recovery_ref,
            }
        )
        self.model.require_original(self.model.binding, model_op, control, live=live)
        if self.site.phase == "open":
            held = self.site.site
            read = self.site.operation.cleanup(
                "task-site-owner-read-" + uuid4().hex,
                now=datetime.now(timezone.utc),
                seconds=min(self.plan.cleanup_seconds, control.checkpoint()),
            )
            record = self.site.journal.read(self.site.spec.token, read)
            if (
                record.state != "acquired"
                or held.ready.worker.owner_guard.controller
                != self.owner.authority.controller.writer
            ):
                raise OwnershipConflict("Original task site is no longer acquired")
            expected = held.ready.controller.target.worker
            if (
                observe_process_cgroup(
                    self.owner.authority.execution,
                    held.ready.worker.owner_guard.worker,
                    control,
                ).membership
                != expected
            ):
                raise OwnershipConflict("Original task site worker/cgroup changed")
        elif live and self.site.phase != "new":
            raise OwnershipConflict("Original task site acquisition is unconfirmed")
        control.checkpoint()
        return plan

    def require_browser(
        self, operation: OperationContext, control: OperationControl
    ) -> RetainedBrowserResource:
        self.require(operation, control, live=True)
        b = self.browser()
        if (
            self.site.phase != "open"
            or b is None
            or b.phase != "open"
            or not isinstance(b.session.engine, SupervisedBrowserSession)
        ):
            raise OwnershipConflict("Actual original fixed browser must be open")
        if (
            b.spec.configuration.spec.scope.task != self.owner.task.identity
            or b.spec.token.owner != self.owner.run.owner
        ):
            raise OwnershipConflict("Original browser changed claimed task/owner")
        engine = b.session.engine
        reply = engine.configuration_reply
        if (
            reply is None
            or reply.owner_guard is None
            or reply.owner_guard.controller != engine.controller
        ):
            raise OwnershipConflict(
                "Original browser guarded configuration return required"
            )
        guard = reply.owner_guard
        read = b.operation.cleanup(
            "task-browser-owner-read-" + uuid4().hex,
            now=datetime.now(timezone.utc),
            seconds=min(self.plan.cleanup_seconds, control.checkpoint()),
        )
        record = b.journal.read(b.spec.token, read)
        if (
            record.state != "acquired"
            or guard.controller != self.owner.authority.controller.writer
        ):
            raise OwnershipConflict("Original browser acquisition/controller changed")
        if len(record.events) != 3 or len(record.events[2].evidence) != 1:
            raise OwnershipConflict(
                "Original complete browser acquisition history required"
            )
        reference = record.events[2].evidence[0]
        held = self.inputs
        if held is not None:
            held.check(operation, control)
        if held is None or held.browser_acquired is None:
            acquired = self.owner.reads.parse(
                reference,
                "browser-worker-acquired/1",
                BrowserWorkerAcquiredFact,
                control,
            )
        else:
            original_ref, acquired = held.browser_acquired
            if original_ref != reference:
                raise OwnershipConflict(
                    "Current browser journal changed original acquired body"
                )
            require_complete_bytes(reference, acquired.model_dump_json().encode())
        acquired.check_spec(b.spec)
        original = acquired.details.prepared
        if original.owner_guard != guard or acquired.operation != phase(
            b.operation, "worker-acquired"
        ):
            raise OwnershipConflict("Browser worker differs from original acquisition")
        # Exact current worker/subtree, not merely another process in this job.
        actual = observe_process_cgroup(
            b.spec.slurm.execution, guard.worker, control
        ).membership
        if actual != original.step.controller.target.worker:
            raise OwnershipConflict("Browser left original task Slurm allocation")
        control.checkpoint()
        if held is not None:
            held.browser_acquired = (reference, acquired)
        return b

    def original_browser_record(
        self, operation: OperationContext, control: OperationControl
    ) -> ResourceRecord:
        b = self.browser()
        if b is None:
            raise OwnershipConflict("Original browser was never constructed")
        read = b.operation.cleanup(
            "task-original-closed-" + uuid4().hex,
            now=datetime.now(timezone.utc),
            seconds=min(self.plan.cleanup_seconds, control.checkpoint()),
        )
        return original_closed_browser(
            b.spec, b.operation, read, b.journal, self.owner.evidence, control
        )

    def verify_closed(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if (
            plan != self.plan
            or closed.reset_plan.scope.owner != self.owner.run.owner
            or closed.reset_plan.scope.task != self.owner.task.identity
        ):
            raise OwnershipConflict("Task closure changed original owner/reset")
        self.require(operation, control, live=False)
        b = self.browser()
        if b is None or b.phase == "unstarted-sealed":
            # Non-start is separately admitted by OriginalTaskNonstartAuthority.
            # Read the original proof bytes, never infer closure from absence.
            holder = self.browser_owner
            if (
                not holder.sealed
                or holder.constructing
                or tuple(c.token for c in closed.closures) != (holder.token,)
                or closed.reset_plan.attempt_allocations != (holder.token,)
            ):
                raise OwnershipConflict(
                    "Original independently sealed non-start owner required"
                )
            for closure, ref in zip(closed.closures, closed.closure_refs, strict=True):
                if (
                    self.owner.evidence.read(ref, control)
                    != closure.model_dump_json().encode()
                    or closure.status != "closed"
                    or not closure.evidence
                ):
                    raise OwnershipConflict(
                        "Original independently admitted non-start closure required"
                    )
                observed = self.owner.reads.parse(
                    closure.evidence[0],
                    "unstarted-task-browser/2",
                    UnstartedTaskBrowser,
                    control,
                )
                if (
                    observed.scope != closed.reset_plan.scope
                    or observed.token != closure.token
                    or observed.token not in closed.reset_plan.attempt_allocations
                ):
                    raise OwnershipConflict(
                        "Non-start proof changed original resource scope"
                    )
            return
        record = self.original_browser_record(operation, control)
        if closed.reset_plan.attempt_allocations != (b.spec.token,) or tuple(
            c.token for c in closed.closures
        ) != (b.spec.token,):
            raise OwnershipConflict("Task closure replaced original browser allocation")
        ending = self.owner.reads.read(record.events[-1].evidence[0], control)
        actual = ClosureReceipt.model_validate_json(
            json.dumps(json.loads(ending)["details"]["closure"])
        )
        if closed.closures != (actual,):
            raise OwnershipConflict(
                "Task closure differs from actual original browser ending"
            )
