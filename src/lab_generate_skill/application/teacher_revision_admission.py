"""Decorate original paid-send authority with the same saved Teacher input proof."""

from lab_generate_skill.domain.model_request import ModelSendPlan, ResolvedModelRequest
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.teacher_revision import TeacherRevisionPlans
from lab_generate_skill.ports.model import ModelSendAuthority
from lab_generate_skill.ports.lifecycle import OperationControls
from .context_review import ContextReviewDeps
from .context_evidence import read_bytes
from .teacher_revision_evidence import review_teacher_input


class TeacherInputSendAuthority:
    def __init__(
        self,
        original: ModelSendAuthority,
        plans: TeacherRevisionPlans,
        review: ContextReviewDeps,
        controls: OperationControls,
    ) -> None:
        if original is None or plans is None:
            raise ValueError(
                "Original source/provider authority and frozen Teacher plans required"
            )
        self.original, self.plans, self.review, self.controls = (
            original,
            plans,
            review,
            controls,
        )

    def verify(self, plan: ModelSendPlan, request: ResolvedModelRequest) -> None:
        control = self.controls.bind(plan.operation)
        self.original.verify(plan, request)
        control.checkpoint()
        bound = self.plans.load(
            request.request.request_id, plan.operation, control=control
        )
        if bound.plan.send != plan or request.request != plan.reservation.request:
            raise OwnershipConflict(
                "Teacher send does not match its original frozen revision plan"
            )
        review_teacher_input(bound, self.review, control=control)
        if (
            read_bytes(
                self.review.evidence,
                plan.input_ref,
                plan.limits.max_input_bytes,
                control,
            )
            != request.input_bytes
            or read_bytes(
                self.review.evidence,
                plan.parameters_ref,
                plan.limits.max_parameters_bytes,
                control,
            )
            != request.parameters_bytes
        ):
            raise OwnershipConflict(
                "Teacher actual sending bytes differ from counted saved input/config"
            )
        self.original.verify(plan, request)
        control.checkpoint()
