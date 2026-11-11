"""Publish existing state facts using selected checks and mandatory authority.

No website/browser action or retry. Reset facts feed existing assemble_reset and
StateRecords; this adapter cannot issue Actor permission or a source claim.
"""

import hashlib
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.reset import (
    ResetPlan,
    ResetInputs,
    TaskResetReceipt,
    EnvironmentResetReceipt,
    ResetHealthReceipt,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.state_qualification import (
    StateQualificationAuthority,
    StateQualificationChecks,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads


class EvidenceStateQualifications:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        checks: StateQualificationChecks,
        authority: StateQualificationAuthority,
    ) -> None:
        self.store, self.controls, self.checks, self.authority = (
            store,
            controls,
            checks,
            authority,
        )
        self.reads = StateReads(store)

    @staticmethod
    def scope(scope: StateScope, operation: OperationContext) -> None:
        if (operation.run_id, operation.owner_id, operation.attempt_id) != (
            scope.owner.run_id,
            scope.owner.owner_id,
            scope.attempt_id,
        ):
            raise OwnershipConflict(
                "Qualification cannot change original run/owner/attempt"
            )

    def put(
        self,
        value: (
            EnvironmentBaseline
            | TaskResetReceipt
            | EnvironmentResetReceipt
            | ResetHealthReceipt
        ),
        control: OperationControl,
    ) -> EvidenceRef:
        raw = value.model_dump_json().encode()
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=value.schema_version,
            visibility="private",
            producer="state-qualifications-v1",
        )
        candidate = evidence_reference(raw, metadata)
        try:
            ref = EvidenceRef.model_validate(
                self.store.put(raw, metadata, control=control)
            )
        except BaseException as error:
            setattr(error, "qualification_candidate_reference", candidate)
            raise
        if ref.model_dump(exclude={"uri"}) != candidate.model_dump(exclude={"uri"}):
            mismatch = EvidenceIntegrityError(
                "Qualification publication changed original bytes/metadata"
            )
            setattr(mismatch, "qualification_candidate_reference", ref)
            raise mismatch
        return ref

    def publish_environment(
        self, selection_ref: EvidenceRef, operation: OperationContext
    ) -> EvidenceRef:
        operation = OperationContext.model_validate(operation)
        control = self.controls.bind(operation)
        selection = self.reads.parse(
            selection_ref, "environment-selection/1", EnvironmentSelection, control
        )
        self.scope(selection.scope, operation)
        if operation.mode != "execute":
            raise ValueError(
                "Initial environment qualification requires execute operation"
            )
        self.authority.verify(
            selection.scope, selection_ref, "environment", operation, control
        )
        value = self.checks.environment(selection, selection_ref, operation, control)
        if value.scope != selection.scope or value.operation != operation:
            raise OwnershipConflict(
                "Environment checker changed original operation/scope"
            )
        reference = self.put(value, control)
        try:
            control.checkpoint()
        except BaseException as error:
            setattr(error, "qualification_reference", reference)
            raise
        return reference

    def load_environment(
        self,
        selection_ref: EvidenceRef,
        reference: EvidenceRef,
        operation: OperationContext,
    ) -> EnvironmentBaseline:
        operation = OperationContext.model_validate(operation)
        control = self.controls.bind(operation)
        selection = self.reads.parse(
            selection_ref, "environment-selection/1", EnvironmentSelection, control
        )
        self.scope(selection.scope, operation)
        value = self.reads.parse(
            reference, "environment-baseline/1", EnvironmentBaseline, control
        )
        self.authority.verify(
            selection.scope, selection_ref, "environment", operation, control
        )
        if value != self.checks.environment(
            selection, selection_ref, value.operation, control
        ):
            raise OwnershipConflict("Environment differs from original measured facts")
        return value

    def publish_reset_facts(
        self, selection_ref: EvidenceRef, operation: OperationContext
    ) -> ResetInputs:
        operation = OperationContext.model_validate(operation)
        control = self.controls.bind(operation)
        selection = self.reads.parse(
            selection_ref, "reset-selection/1", ResetSelection, control
        )
        plan = self.reads.parse(selection.plan_ref, "reset-plan/1", ResetPlan, control)
        self.scope(plan.scope, operation)
        if (
            operation.mode != "cleanup"
            or operation.parent_operation_id != plan.parent_operation_id
        ):
            raise OwnershipConflict(
                "Reset qualification requires original execution parent"
            )
        self.authority.verify(plan.scope, selection_ref, "reset", operation, control)
        qualified = self.checks.reset(selection, selection_ref, control)
        if (
            qualified.plan != plan
            or operation.allocation_id != qualified.allocation_id
            or operation.recovery_ref != plan.environment_recovery_ref
        ):
            raise OwnershipConflict(
                "Reset checker changed original plan/allocation/recovery"
            )

        def phase(name: str, recovery: EvidenceRef) -> OperationContext:
            return operation.model_copy(
                update={
                    "operation_id": "state-"
                    + name
                    + "-"
                    + hashlib.sha256(operation.operation_id.encode()).hexdigest(),
                    "recovery_ref": recovery,
                }
            )

        references: list[EvidenceRef] = []
        try:
            task = TaskResetReceipt(
                scope=plan.scope,
                operation=phase("task", plan.task_recovery_ref),
                recovery_ref=plan.task_recovery_ref,
                after_closure_refs=selection.closure_refs,
                checks=qualified.task,
            )
            task_ref = self.put(task, control)
            references.append(task_ref)
            control.checkpoint()
            environment = EnvironmentResetReceipt(
                scope=plan.scope,
                operation=phase("environment", plan.environment_recovery_ref),
                recovery_ref=plan.environment_recovery_ref,
                after_task_reset_ref=task_ref,
                checks=qualified.environment,
            )
            environment_ref = self.put(environment, control)
            references.append(environment_ref)
            control.checkpoint()
            health = ResetHealthReceipt(
                scope=plan.scope,
                operation=phase("health", plan.environment_recovery_ref),
                after_environment_reset_ref=environment_ref,
                checks=qualified.health,
            )
            health_ref = self.put(health, control)
            references.append(health_ref)
            control.checkpoint()
            return ResetInputs(
                plan=plan,
                plan_ref=selection.plan_ref,
                spec=qualified.spec,
                task_recovery=qualified.task_recovery,
                environment_recovery=qualified.environment_recovery,
                closures=qualified.closures,
                closure_refs=selection.closure_refs,
                task=task,
                task_ref=task_ref,
                environment=environment,
                environment_ref=environment_ref,
                health=health,
                health_ref=health_ref,
            )
        except BaseException as error:
            setattr(error, "qualification_references", tuple(references))
            raise
