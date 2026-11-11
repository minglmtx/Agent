"""Current TaskFinalization on original owned browser and native recovery ports.

Physical close is attempted before optional metadata checks; no restoration
until complete original closure, source permission and snapshot facts agree.
Every restore/resume attempt is single-use, including partial publication.
"""

import os
import threading
from lab_generate_skill.adapters.browsergym.task_finalization import (
    OriginalTaskBrowserFinalizer,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.storage.capture_evidence import CaptureEvidence
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan, ResetReceipt, assemble_reset
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.state_qualification import (
    ResetSelection,
    EnvironmentSelection,
)
from lab_generate_skill.domain.task_execution import (
    TaskExecutionPlan,
    ClosedTaskResources,
)
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.site_resume import SiteResumeAuthority
from lab_generate_skill.ports.state_qualification import ResetQualifications
from lab_generate_skill.ports.state_records import (
    StateRecords,
    VerifiedResetPublication,
    ResetInputPublication,
)
from lab_generate_skill.ports.task_finalization import (
    TaskFinalizationAuthority,
    TaskFinalizationDeclarationInputs,
)
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from .recorded_resume import RecordedSiteResume
from .task_preparation import RecordedSiteTaskPreparation
from .task_finalization_state import TaskFinalizationState


class TaskFinalizationUnconfirmed(RuntimeError):
    def __init__(
        self,
        primary: BaseException,
        state: TaskFinalizationState,
        browser: OriginalTaskBrowserFinalizer,
        writer: CaptureEvidence,
        failed_phase: str,
    ) -> None:
        self.primary, self.state, self.failed_phase = primary, state, failed_phase
        refs = [*state.references, *browser.references]
        for name in (
            "reference",
            "resume_intent_reference",
            "resume_result_reference",
            "browser_resource_ending_ref",
        ):
            value = getattr(primary, name, None)
            if isinstance(value, EvidenceRef):
                refs.append(value)
        value = getattr(primary, "qualification_references", ())
        if isinstance(value, tuple):
            refs.extend(ref for ref in value if isinstance(ref, EvidenceRef))
        candidates = [*writer.candidates, *browser.writer.candidates]
        for name in (
            "resume_candidate_reference",
            "qualification_candidate_reference",
            "state_candidate_reference",
        ):
            value = getattr(primary, name, None)
            if isinstance(value, EvidenceRef):
                candidates.append(value)
        self.references, self.candidates = tuple(dict.fromkeys(refs)), tuple(
            dict.fromkeys(candidates)
        )
        self.known_closed, self.known_reset = state.closed, state.reset
        super().__init__(
            "Original finalization unconfirmed; retain facts/owner and never repeat restore or resume"
        )


class RecordedTaskFinalization:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        declaration_ref: EvidenceRef,
        reset: ResetPlan,
        preparation: RecordedSiteTaskPreparation,
        browser: OriginalTaskBrowserFinalizer,
        qualifications: ResetQualifications,
        states: StateRecords,
        authority: TaskFinalizationAuthority,
        resume_authority: SiteResumeAuthority,
        evidence: EvidenceStore,
        controls: OperationControls,
        state: TaskFinalizationState,
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        self.declaration = TaskFinalizationPlan.model_validate(declaration)
        self.reset = ResetPlan.model_validate(reset)
        if any(
            x is None
            for x in (
                preparation,
                browser,
                qualifications,
                states,
                authority,
                resume_authority,
                evidence,
                controls,
                state,
            )
        ):
            raise ValueError(
                "All original recovery, physical and state authorities are mandatory"
            )
        if (
            preparation.plan != self.plan
            or preparation.declaration.scope != self.reset.scope
            or self.declaration.scope != self.reset.scope
            or self.reset.scope.owner != plan.intent.binding.run.owner
            or self.reset.scope.task != plan.intent.binding.task
            or self.reset.scope.attempt_id != plan.intent.binding.attempt_id
        ):
            raise OwnershipConflict(
                "Original task finalization scope/preparation/reset required"
            )
        self.declaration_ref, self.preparation, self.browser = (
            declaration_ref,
            preparation,
            browser,
        )
        self.qualifications, self.states, self.authority = (
            qualifications,
            states,
            authority,
        )
        self.resume_authority, self.evidence, self.controls, self.state = (
            resume_authority,
            evidence,
            controls,
            state,
        )
        self.writer, self.reads = CaptureEvidence(
            evidence, "task-finalization-v1"
        ), StateReads(evidence)
        self.owner = os.getpid(), threading.get_ident()

    def _entry(self, plan: TaskExecutionPlan, operation: OperationContext) -> None:
        if (
            self.owner != (os.getpid(), threading.get_ident())
            or TaskExecutionPlan.model_validate(plan) != self.plan
        ):
            raise OwnershipConflict("Finalization changed original controller/plan")
        operation = OperationContext.model_validate(operation)
        if (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.mode,
            operation.parent_operation_id,
            operation.allocation_id,
            operation.recovery_ref,
        ) != (
            self.reset.scope.owner.run_id,
            self.reset.scope.owner.owner_id,
            self.reset.scope.attempt_id,
            "cleanup",
            self.plan.operation.operation_id,
            None,
            None,
        ):
            raise OwnershipConflict(
                "Finalization requires original task cleanup parent/scope"
            )

    def _declaration_bytes(
        self,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> bytes:
        if isinstance(self.authority, TaskFinalizationDeclarationInputs):
            return self.authority.read_finalization_declaration(
                self.plan, self.declaration, reference, operation, control
            )
        return self.reads.read(reference, control)

    def _metadata(self, operation: OperationContext, control: OperationControl) -> None:
        if self.controls.bind(operation).checkpoint() > self.plan.cleanup_seconds:
            raise OwnershipConflict("Cleanup operation widened original task budget")
        ref = self.declaration_ref
        raw = self._declaration_bytes(ref, operation, control)
        require_complete_bytes(ref, raw)
        if (ref.content_schema, ref.visibility, ref.media_type) != (
            self.declaration.schema_version,
            "private",
            "application/json",
        ) or raw != self.declaration.model_dump_json().encode():
            raise OwnershipConflict("Original frozen finalization declaration changed")
        reset_raw = self._declaration_bytes(
            self.plan.reset_plan_ref, operation, control
        )
        require_complete_bytes(self.plan.reset_plan_ref, reset_raw)
        if self.plan.reset_plan_ref.content_schema != "reset-plan/1":
            raise OwnershipConflict("Original frozen ResetPlan schema changed")
        reset = ResetPlan.model_validate_json(reset_raw)
        if reset != self.reset:
            raise OwnershipConflict("Original frozen ResetPlan changed")
        self.authority.verify(
            self.plan,
            self.declaration,
            tuple(
                dict.fromkeys(
                    (
                        *self.preparation.state.references,
                        *self.state.references,
                        *self.browser.references,
                    )
                )
            ),
            operation,
            control,
        )

    def close(
        self,
        plan: TaskExecutionPlan,
        reset: ResetPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosedTaskResources:
        self._entry(plan, operation)
        if ResetPlan.model_validate(reset) != self.reset:
            raise OwnershipConflict("Cannot close another original reset domain")
        s = self.state
        if s.close_attempted:
            raise DispatchAlreadyCommitted(
                "Task close already attempted; inspect original resource ending only"
            )
        s.close_attempted, s.phase = True, "browser-close"
        try:
            # Original retained component independently performs bounded close
            # even if task metadata bookkeeping has failed. No native restore here.
            closure, ref = self.browser.close(
                plan, self.declaration, self.declaration_ref, reset, operation, control
            )
            s.references.extend(self.browser.references)
            s.phase = "close-admission"
            s.closed = ClosedTaskResources(
                reset_plan=reset,
                reset_plan_ref=plan.reset_plan_ref,
                closures=(closure,),
                closure_refs=(ref,),
            )
            self._metadata(operation, control)
            control.checkpoint()
            s.phase = "closed"
            return s.closed
        except BaseException as error:
            phase = s.phase
            s.phase = (
                "close-admission-unconfirmed"
                if phase == "close-admission" and s.closed is not None
                else "quarantined"
            )
            raise TaskFinalizationUnconfirmed(
                error, s, self.browser, self.writer, phase
            ) from error

    def restore(
        self,
        plan: TaskExecutionPlan,
        closed: ClosedTaskResources,
        operation: OperationContext,
        control: OperationControl,
    ) -> EvidenceRef:
        self._entry(plan, operation)
        s, d, p = self.state, self.declaration, self.preparation
        if s.restore_attempted:
            raise DispatchAlreadyCommitted(
                "Original restore/resume already attempted; never redispatch"
            )
        if (
            s.phase not in ("closed", "close-admission-unconfirmed")
            or s.closed is None
            or ClosedTaskResources.model_validate(closed) != s.closed
        ):
            raise OwnershipConflict(
                "Original confirmed closed domain required before restore"
            )
        s.restore_attempted, s.phase = True, "restore-admission"
        try:
            self._metadata(operation, control)
            # The original frozen ResetPlan/Map reset contract names prepare,
            # while a snapshot-only native worker names snapshot as its parent.
            # Missing/unknown prepare confirmation cannot select that branch or
            # be repaired by guessing IDs. Never dispatch an ineligible restore.
            if (
                p.state.prepare_request is None
                or p.state.prepare_result is None
                or p.state.prepare_request_ref is None
                or p.state.prepare_result_ref is None
            ):
                raise OwnershipConflict(
                    "Original prepare confirmation unavailable for frozen reset parent; no restore dispatched"
                )
            prepared_request = self.reads.parse(
                p.state.prepare_request_ref,
                "site-task-request/2",
                SiteTaskRequest,
                control,
            )
            prepared_result = self.reads.parse(
                p.state.prepare_result_ref,
                "site-task-result/1",
                SiteTaskResult,
                control,
            )
            if (
                prepared_request != p.state.prepare_request
                or prepared_result != p.state.prepare_result
                or prepared_request.action != "prepare"
                or prepared_request.operation != p.declaration.prepare_operation
                or prepared_request.operation.operation_id
                != self.reset.parent_operation_id
                or prepared_result.request_sha256 != prepared_request.digest
                or prepared_request.snapshot_ref != p.state.snapshot_ref
            ):
                raise OwnershipConflict(
                    "Original prepare confirmation changed frozen restore lineage"
                )
            snapshot_ref, snapshot_request, env_ref = (
                p.state.snapshot_ref,
                p.state.snapshot_request,
                p.state.environment_selection_ref,
            )
            if (
                snapshot_ref is None
                or snapshot_request is None
                or env_ref is None
                or p.state.snapshot_request_ref is None
                or p.state.snapshot_result_ref is None
            ):
                raise OwnershipConflict(
                    "Original complete snapshot/environment facts unavailable; no restore dispatched"
                )
            actual_request = self.reads.parse(
                p.state.snapshot_request_ref,
                "site-task-request/2",
                SiteTaskRequest,
                control,
            )
            actual_result = self.reads.parse(
                p.state.snapshot_result_ref,
                "site-task-result/1",
                SiteTaskResult,
                control,
            )
            env = self.reads.parse(
                env_ref, "environment-selection/1", EnvironmentSelection, control
            )
            if (
                actual_request != snapshot_request
                or actual_request.action != "snapshot"
                or actual_result.request_sha256 != actual_request.digest
                or snapshot_ref.content_schema != p.declaration.snapshot_schema
                or env.scope != self.reset.scope
                or env.snapshot_ref != snapshot_ref
                or env.site_spec_ref != p.declaration.site_spec_ref
                or env.site_started_ref != p.state.original_acquired().site_started_ref
            ):
                raise OwnershipConflict(
                    "Original complete snapshot/site/environment lineage changed"
                )
            require_complete_bytes(snapshot_ref, self.reads.read(snapshot_ref, control))
            restore_op = operation.model_copy(
                update={
                    "operation_id": d.restore_operation_id,
                    "parent_operation_id": self.reset.parent_operation_id,
                    "allocation_id": p.spec.token.allocation_id,
                    "recovery_ref": self.reset.task_recovery_ref,
                }
            )
            s.restore_request = snapshot_request.model_copy(
                update={
                    "action": "restore",
                    "operation": restore_op,
                    "snapshot_ref": snapshot_ref,
                }
            )
            s.phase = "restoring"
            s.restore_request_ref = self.writer.put(
                s.restore_request.model_dump_json().encode(),
                s.restore_request.schema_version,
                control,
            )
            s.references.append(s.restore_request_ref)
            self._metadata(restore_op, self.controls.bind(restore_op))
            s.restore_result = SiteTaskResult.model_validate(
                p.site.tasks.execute_task(
                    s.restore_request, control=self.controls.bind(restore_op)
                )
            )
            s.restore_result_ref = self.writer.put(
                s.restore_result.model_dump_json().encode(),
                s.restore_result.schema_version,
                control,
            )
            s.references.append(s.restore_result_ref)
            if s.restore_result.request_sha256 != s.restore_request.digest:
                raise OwnershipConflict(
                    "Restore returned another original request result"
                )
            resume_op = restore_op.model_copy(
                update={
                    "operation_id": d.resume_operation_id,
                    "parent_operation_id": restore_op.operation_id,
                    "recovery_ref": self.reset.environment_recovery_ref,
                }
            )
            s.resume_request = SiteResumeRequest(
                restore_request=s.restore_request,
                restore_result_ref=s.restore_result_ref,
                operation=resume_op,
            )
            s.phase = "resuming"
            s.resume_request_ref = self.writer.put(
                s.resume_request.model_dump_json().encode(),
                s.resume_request.schema_version,
                control,
            )
            s.references.append(s.resume_request_ref)
            self._metadata(resume_op, self.controls.bind(resume_op))
            resume = RecordedSiteResume(
                p.site.resume, self.evidence, self.resume_authority
            )
            s.resume_result_ref = resume.resume(
                s.resume_request, control=self.controls.bind(resume_op)
            )
            if resume.intent_ref is None:
                raise OwnershipConflict("Original resume intent was not confirmed")
            s.resume_intent_ref = resume.intent_ref
            s.references.extend((s.resume_intent_ref, s.resume_result_ref))
            s.phase = "qualifying"
            s.reset_selection = ResetSelection(
                environment_selection_ref=env_ref,
                plan_ref=self.plan.reset_plan_ref,
                restore_request_ref=s.restore_request_ref,
                restore_result_ref=s.restore_result_ref,
                resume_request_ref=s.resume_request_ref,
                resume_result_ref=s.resume_result_ref,
                resume_intent_ref=s.resume_intent_ref,
                closure_refs=closed.closure_refs,
            )
            s.reset_selection_ref = self.writer.put(
                s.reset_selection.model_dump_json().encode(),
                s.reset_selection.schema_version,
                control,
            )
            s.references.append(s.reset_selection_ref)
            qualified_op = operation.model_copy(
                update={
                    "operation_id": d.qualification_operation_id,
                    "parent_operation_id": self.reset.parent_operation_id,
                    "allocation_id": p.spec.token.allocation_id,
                    "recovery_ref": self.reset.environment_recovery_ref,
                }
            )
            self._metadata(qualified_op, self.controls.bind(qualified_op))
            s.reset_inputs = self.qualifications.publish_reset_facts(
                s.reset_selection_ref, qualified_op
            )
            reset_op = qualified_op.model_copy(
                update={"operation_id": d.reset_operation_id}
            )
            s.reset = assemble_reset(s.reset_inputs, reset_op)
            if isinstance(self.states, ResetInputPublication):
                s.reset_publication = self.states.publish_reset_inputs(
                    s.reset, s.reset_inputs, reset_op
                )
                s.reset_ref = s.reset_publication.reference
                s.references.append(s.reset_ref)
            elif isinstance(self.states, VerifiedResetPublication):
                s.reset_ref = self.states.publish_reset_verified(s.reset, reset_op)
                s.references.append(s.reset_ref)
            else:
                s.reset_ref = self.states.publish_reset(s.reset, reset_op)
                s.references.append(s.reset_ref)
                if self.states.load_reset(s.reset_ref, reset_op) != s.reset:
                    raise OwnershipConflict(
                        "Original full reset/health facts are not safe"
                    )
            if s.reset.status != "safe":
                raise OwnershipConflict("Original full reset/health facts are not safe")
            control.checkpoint()
            s.phase = "restored"
            return s.reset_ref
        except BaseException as error:
            phase, s.phase = s.phase, "quarantined"
            raise TaskFinalizationUnconfirmed(
                error, s, self.browser, self.writer, phase
            ) from error

    def load_restored_reset(
        self,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> ResetReceipt:
        self._entry(self.plan, operation)
        control.checkpoint()
        state = self.state
        if state.phase != "restored" or state.reset_ref != reference:
            raise OwnershipConflict(
                "Reset consumption changed this original completed restoration"
            )
        if state.reset_publication is not None:
            if not isinstance(self.states, ResetInputPublication):
                raise OwnershipConflict("Original Reset publication consumer changed")
            receipt = self.states.load_reset_publication(
                state.reset_publication, operation
            )
        else:
            receipt = self.states.load_reset(reference, operation)
        if receipt != state.reset:
            raise OwnershipConflict(
                "Reset consumption changed this original receipt body"
            )
        control.checkpoint()
        return receipt
