"""Route each explicit original Teacher proof; no model or fee dependencies."""

from dataclasses import dataclass
from lab_generate_skill.domain.construction import CallCompleted
from lab_generate_skill.domain.construction_inputs import RevisionResult
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.review import ReviewPlan, ReviewTeacher
from lab_generate_skill.domain.teacher_revision import TeacherCompletion
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from .teacher_assembly_review import TeacherAssemblyReviewDeps, review_teacher_assembly
from .review_controls import ReviewControl


@dataclass(frozen=True)
class ReviewTeacherService:
    declared: ReviewTeacher
    assembly: TeacherAssemblyReviewDeps
    response: TeacherConstructionVerifier


class ConstructionTeacherReviews:
    def __init__(
        self,
        plan: ReviewPlan,
        sealed: ConstructionProgress,
        services: tuple[ReviewTeacherService, ...],
        controls: OperationControls,
    ) -> None:
        self.plan, self.sealed, self.controls = plan, sealed, controls
        if (
            type(services) is not tuple
            or tuple(s.declared for s in services) != plan.teachers
        ):
            raise ValueError(
                "Every original Teacher assembly needs its exact explicit proof service"
            )
        self.services = {
            s.declared.published.bound.plan.revision.request_id: s for s in services
        }

    def verify_construction(
        self,
        progress: ConstructionProgress,
        event: CallCompleted,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> TeacherCompletion:
        result = event.response
        if (
            not isinstance(result, RevisionResult)
            or result.schema_version != "revision-result/2"
            or operation != self.plan.operation
        ):
            raise EvidenceIntegrityError(
                "Original Teacher v2/current review operation required"
            )
        if (
            progress.plan != self.sealed.plan
            or self.sealed.events[: len(progress.events)] != progress.events
        ):
            raise EvidenceIntegrityError(
                "Teacher proof changed original sealed construction prefix"
            )
        service = self.services.get(result.request_id)
        if service is None:
            raise EvidenceIntegrityError("No exact declared original Teacher proof")
        item = service.declared
        leaf = ReviewControl(control, self.controls.bind(item.operation))
        leaf.checkpoint()
        review_teacher_assembly(
            item.published, service.assembly, item.operation, control=leaf
        )
        completion = service.response.verify_construction(
            progress, event, item.operation, control=leaf
        )
        leaf.checkpoint()
        return TeacherCompletion.model_validate(completion)
