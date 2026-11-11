"""Readonly original Teacher result/ledger receipt/response review after closure."""

from lab_generate_skill.domain.construction_inputs import RevisionInput, RevisionResult
from lab_generate_skill.domain.teacher_revision import (
    TeacherCompletion,
    BoundTeacherRevisionPlan,
)
from lab_generate_skill.domain.construction import CallCompleted
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from lab_generate_skill.ports.lifecycle import OperationControl
from .context_evidence import read_bytes
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.teacher_revision import (
    TeacherRevisionPlans,
    TeacherCompletionDecoder,
)
from .context_review import ContextReviewDeps
from .teacher_revision_evidence import (
    review_teacher_input,
    read_teacher_execution,
    original_teacher_response,
    check_teacher_completion,
)


class RecordedTeacherRevisionReview:
    def __init__(
        self,
        plans: TeacherRevisionPlans,
        evidence: EvidenceReader,
        controls: OperationControls,
        review: ContextReviewDeps,
        decoder: TeacherCompletionDecoder,
    ) -> None:
        self.plans, self.evidence, self.controls, self.review, self.decoder = (
            plans,
            evidence,
            controls,
            review,
            decoder,
        )

    def verify(
        self, request: RevisionInput, result: RevisionResult, op: OperationContext
    ) -> TeacherCompletion:
        request = RevisionInput.model_validate(request)
        result = RevisionResult.model_validate(result)
        op = OperationContext.model_validate(op)
        if (
            op.mode != "cleanup"
            or result.schema_version != "revision-result/2"
            or result.execution_ref is None
        ):
            raise OwnershipConflict(
                "Readonly Teacher verification requires original v2 execution, never a new call"
            )
        control = self.controls.bind(op)
        bound = self.plans.load(request.request_id, op, control=control)
        plan = bound.plan
        if request != plan.revision:
            raise OwnershipConflict("Teacher review changed original revision")
        return self._verify_bound(bound, result, control=control)

    def verify_construction(
        self,
        progress: ConstructionProgress,
        event: CallCompleted,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> TeacherCompletion:
        """Read original proof under the journal's bounded command, never dispatch.

        This is the same proof as closed review; construction may reconcile a
        returned fact under cleanup without renewing the original send deadline.
        Its original source/writer authority remains mandatory at the journal.
        """
        progress = ConstructionProgress.model_validate(progress)
        event = CallCompleted.model_validate(event)
        operation = OperationContext.model_validate(operation)
        result = event.response
        if (
            not isinstance(result, RevisionResult)
            or result.schema_version != "revision-result/2"
        ):
            raise OwnershipConflict("Construction review requires explicit Teacher v2")
        control.checkpoint()
        bound = self.plans.load_recorded(result.request_id, operation, control=control)
        plan = bound.plan
        scope = plan.preparation.scope
        pending = progress.project().pending_call
        if (
            not isinstance(scope, TeacherContextScope)
            or pending != plan.call
            or progress.plan.run.owner != scope.owner
            or progress.plan.task.identity != scope.task
        ):
            raise OwnershipConflict(
                "Teacher result changed original construction/source/call"
            )
        model = next(item for item in progress.plan.models if item.role == "teacher")
        if (
            model.model_binding_ref,
            model.parameters_ref,
            model.model,
            model.provider,
            model.paid,
        ) != (
            plan.call.model_binding_ref,
            plan.call.base_parameters_ref,
            plan.preparation.profile.model,
            plan.preparation.profile.provider,
            True,
        ):
            raise OwnershipConflict(
                "Teacher result changed frozen construction model parameters"
            )
        public = PublicConstructionContext.model_validate_json(
            read_bytes(
                self.evidence, progress.plan.public_context_ref, 1024**2, control
            )
        )
        if (public.context_id, public.task.identity) != (scope.context_id, scope.task):
            raise OwnershipConflict("Teacher result changed qualified public context")
        return self._verify_bound(bound, result, control=control)

    def _verify_bound(
        self,
        bound: BoundTeacherRevisionPlan,
        result: RevisionResult,
        *,
        control: OperationControl,
    ) -> TeacherCompletion:
        plan = bound.plan
        request = plan.revision
        if result.execution_ref is None:
            raise EvidenceIntegrityError("Original Teacher execution evidence required")
        receipt = review_teacher_input(bound, self.review, control=control)
        execution = read_teacher_execution(
            result.execution_ref, self.evidence, control=control
        )
        if execution.plan_ref != bound.reference:
            raise EvidenceIntegrityError(
                "Teacher execution came from another source/format/plan"
            )
        returned = execution.send_result
        raw = original_teacher_response(bound, returned, self.evidence, control=control)
        completion = self.decoder.decode(raw)
        check_teacher_completion(bound, receipt, returned, completion)
        expected = RevisionResult(
            schema_version="revision-result/2",
            request_id=request.request_id,
            input_sha256=plan.call.input_ref.sha256,
            parameters_sha256=plan.call.parameters_ref.sha256,
            skill=completion.skill,
            response_ref=returned.fact.response_ref,
            execution_ref=result.execution_ref,
        )
        if result != expected:
            raise EvidenceIntegrityError(
                "Teacher revision/export changed actual source/input/parameters/skill/response"
            )
        return completion
