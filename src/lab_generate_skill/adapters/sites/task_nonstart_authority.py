"""Original exclusive browser non-start proof over retained state and journal.

An unfinished factory, registration, acquiring event or lost acknowledgement is
never absence. Sealing the original holder prevents a subsequent local launch.
"""

from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import (
    TaskFinalizationPlan,
    UnstartedTaskBrowser,
)
from lab_generate_skill.ports.lifecycle import OperationControl


class OriginalTaskNonstartAuthority:
    def __init__(self, resources: OriginalTaskResourceOwner) -> None:
        if not isinstance(resources, OriginalTaskResourceOwner):
            raise TypeError("Original task resource owner required")
        self.resources = resources

    def close_unstarted(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        observed: UnstartedTaskBrowser,
        observed_ref: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        r, holder = self.resources, self.resources.browser_owner
        observed = UnstartedTaskBrowser.model_validate(observed)
        operation = OperationContext.model_validate(operation)
        if (
            plan != r.plan
            or observed.operation != operation
            or observed.token != holder.token
            or observed.scope != declaration.scope
            or observed.scope.owner != r.owner.run.owner
            or observed.scope.task != r.owner.task.identity
            or observed.scope.attempt_id != plan.intent.binding.attempt_id
            or observed.reset_plan_ref != plan.reset_plan_ref
            or observed.preparation_declaration_ref != plan.declaration_ref
            or operation.mode != "cleanup"
            or operation.parent_operation_id != plan.operation.operation_id
            or operation.operation_id != declaration.browser_close_operation_id
        ):
            raise OwnershipConflict(
                "Non-start changed original task/cleanup declaration"
            )
        r.require(operation, control, live=False)
        if (
            r.owner.reads.read(observed_ref, control)
            != observed.model_dump_json().encode()
            or observed_ref.content_schema != observed.schema_version
            or observed_ref.visibility != "private"
        ):
            raise OwnershipConflict("Non-start original observation bytes changed")
        declared = r.owner.reads.parse(
            observed.finalization_declaration_ref,
            "task-finalization-plan/1",
            TaskFinalizationPlan,
            control,
        )
        if declared != declaration:
            raise OwnershipConflict(
                "Non-start changed original finalization declaration"
            )
        b = holder.original()
        if (
            observed.owner_phase != ("not_constructed" if b is None else "new")
            or holder.constructing
            or holder.sealed
        ):
            raise OwnershipConflict(
                "Interrupted/consumed browser factory cannot prove non-start"
            )
        if b is not None and (
            b.spec.token != observed.token
            or b.journal is not holder.journal
            or b.phase != "new"
            or b.manager is not None
            or b.open_error is not None
        ):
            raise OwnershipConflict(
                "Original browser acquisition was already attempted"
            )
        # records() validates the retained namespace and rejects corrupt or
        # incomplete history. Do not catch integrity errors as missing data.
        records = holder.journal.records(observed.token.owner, operation)
        if any(
            record.token.allocation_id == observed.token.allocation_id
            for record in records
        ):
            raise OwnershipConflict("Original browser registration/acquisition exists")
        r.owner.caller(operation, control)
        control.checkpoint()
        holder.seal_unstarted()
        return ClosureReceipt(
            token=observed.token,
            operation_id=operation.operation_id,
            status="closed",
            evidence=(observed_ref,),
        )
