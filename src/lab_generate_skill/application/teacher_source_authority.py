"""Require the same original source receipt in prepare, send and closed review."""

from lab_generate_skill.domain.teacher_source import PublishedTeacherSource
from lab_generate_skill.domain.context_preparation import ContextPreparationRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.context_projection import ContextPreparationAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from .teacher_source_review import TeacherSourceReviewDeps, review_teacher_source


class RecordedTeacherSourceAuthority:
    def __init__(
        self,
        original: ContextPreparationAuthority,
        published: PublishedTeacherSource,
        deps: TeacherSourceReviewDeps,
    ) -> None:
        if original is None or deps.authority is None:
            raise ValueError("Original source authority required; no default allow")
        self.original, self.published, self.deps = (
            original,
            PublishedTeacherSource.model_validate(published),
            deps,
        )

    def _source(
        self, request: ContextPreparationRequest, control: OperationControl
    ) -> None:
        receipt = review_teacher_source(self.published, self.deps, control=control)
        if (
            request.source != receipt.source
            or request.request_id != receipt.bindings.request_id
            or request.operation != receipt.bindings.operation
        ):
            raise OwnershipConflict(
                "Teacher preparation/send changed original source history/request/operation"
            )

    def verify_prepare(
        self, request: ContextPreparationRequest, *, control: OperationControl
    ) -> None:
        self.original.verify_prepare(request, control=control)
        self._source(request, control)

    def verify_recorded(
        self,
        request: ContextPreparationRequest,
        reference: EvidenceRef,
        *,
        control: OperationControl,
    ) -> None:
        self.original.verify_recorded(request, reference, control=control)
        self._source(request, control)
