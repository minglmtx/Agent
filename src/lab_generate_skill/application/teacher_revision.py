"""Teacher.revise over original prepared facts and original PaidModelSender.

No runner, retry, fee ledger, browser or concrete role/site implementation here.
The bootstrap composes the original source authority with the saved input gate.
"""

from lab_generate_skill.domain.construction_inputs import RevisionInput, RevisionResult
from lab_generate_skill.domain.teacher_revision import TeacherRevisionExecution
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_response import ModelSendResult
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.model import PaidModelSender
from lab_generate_skill.ports.teacher_revision import (
    TeacherRevisionPlans,
    TeacherCompletionDecoder,
)
from .context_review import ContextReviewDeps
from .context_evidence import publish_raw
from .teacher_revision_evidence import (
    review_teacher_input,
    original_teacher_response,
    check_teacher_completion,
)


class TeacherRevisionUnconfirmed(RuntimeError):
    def __init__(
        self,
        stage: str,
        returned: ModelSendResult,
        retained: tuple[EvidenceRef, ...],
        primary: BaseException,
    ) -> None:
        self.stage, self.returned, self.retained, self.primary = (
            stage,
            returned,
            retained,
            primary,
        )
        super().__init__(
            "Original Teacher result unresolved; preserve known send facts and never resend"
        )


class TeacherRevisionResponseRejected(TeacherRevisionUnconfirmed):
    """Known original returned response/cost, not a native task failure or retry."""


class RecordedTeacher:
    def __init__(
        self,
        plans: TeacherRevisionPlans,
        sender: PaidModelSender,
        evidence: EvidenceStore,
        controls: OperationControls,
        review: ContextReviewDeps,
        decoder: TeacherCompletionDecoder,
    ) -> None:
        (
            self.plans,
            self.sender,
            self.evidence,
            self.controls,
            self.review,
            self.decoder,
        ) = (plans, sender, evidence, controls, review, decoder)

    def revise(self, request: RevisionInput, op: OperationContext) -> RevisionResult:
        request = RevisionInput.model_validate(request)
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        control.checkpoint()
        bound = self.plans.load(request.request_id, op, control=control)
        plan = bound.plan
        if (
            op.mode != "execute"
            or op != plan.send.operation
            or request != plan.revision
        ):
            raise OwnershipConflict(
                "Teacher revision requires original registered request and execute operation"
            )
        receipt = review_teacher_input(bound, self.review, control=control)
        # The original sender alone reserves, commits dispatch and settles. Its
        # composition rechecks the same proof at the actual one-send boundary.
        returned = ModelSendResult.model_validate(self.sender.generate(plan.send))
        retained: list[EvidenceRef] = []
        stage = "save_original_return"
        try:
            result_control = self.controls.bind(plan.send.settlement_operation)
            execution = TeacherRevisionExecution(
                plan_ref=bound.reference, send_result=returned
            )
            ref = publish_raw(
                self.evidence,
                execution.model_dump_json().encode(),
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema="teacher-revision-execution/1",
                    visibility="private",
                    producer="original-teacher-revision",
                ),
                retained,
                result_control,
            )
            stage = "read_original_response"
            raw = original_teacher_response(
                bound, returned, self.evidence, control=result_control
            )
            stage = "decode_original_response"
            completion = self.decoder.decode(raw)
            stage = "reconcile_original_usage"
            check_teacher_completion(bound, receipt, returned, completion)
            result_control.checkpoint()
            return RevisionResult(
                schema_version="revision-result/2",
                request_id=request.request_id,
                input_sha256=plan.call.input_ref.sha256,
                parameters_sha256=plan.call.parameters_ref.sha256,
                skill=completion.skill,
                response_ref=returned.fact.response_ref,
                execution_ref=ref,
            )
        except (ValueError, OperationStopped) as error:
            kind = (
                TeacherRevisionUnconfirmed
                if isinstance(error, OperationStopped)
                else TeacherRevisionResponseRejected
            )
            raise kind(stage, returned, tuple(retained), error) from error
        except BaseException as error:
            raise TeacherRevisionUnconfirmed(
                stage, returned, tuple(retained), error
            ) from error
