"""Replay original content verification over a sealed immutable construction.

Reuse ConstructionEvidence's actual context/retrieval/call/response checks and
explicit recorded authorities. This adapter has no journal writer or transport.
"""

from .construction_evidence import ConstructionEvidence
from lab_generate_skill.domain.construction_state import (
    ConstructionProgress,
    append_construction_event,
)
from lab_generate_skill.domain.construction import CallCompleted
from lab_generate_skill.domain.construction_inputs import RevisionResult
from lab_generate_skill.domain.review import ReviewPlan
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.construction import ConstructionJournal


class RecordedConstructionHistory:
    def __init__(
        self,
        original: ConstructionEvidence,
        plan: ReviewPlan,
        sealed: ConstructionProgress,
        journal: ConstructionJournal,
    ) -> None:
        if original is None or not callable(getattr(journal, "read", None)):
            raise ValueError(
                "Original complete recorded construction verifier required"
            )
        self.original, self.plan, self.sealed = (
            original,
            ReviewPlan.model_validate(plan),
            ConstructionProgress.model_validate(sealed),
        )
        self.journal = journal

    def verify_current(
        self,
        progress: ConstructionProgress,
        plan: ReviewPlan,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if (
            plan != self.plan
            or progress != self.sealed
            or self.journal.read(plan.operation) != progress
        ):
            raise EvidenceIntegrityError(
                "Sealed review is not the original persisted construction history"
            )
        control.checkpoint()

    def verify(
        self,
        progress: ConstructionProgress,
        plan: ReviewPlan,
        control: OperationControl,
    ) -> None:
        self.verify_current(progress, plan, control)
        expected = tuple(
            t.published.bound.plan.revision.request_id for t in plan.teachers
        )
        recorded = tuple(
            e.response.request_id
            for e in progress.events
            if isinstance(e, CallCompleted) and isinstance(e.response, RevisionResult)
        )
        if recorded != expected:
            raise EvidenceIntegrityError(
                "Every original Teacher call must retain its assembly/response proof"
            )
        self.original.plan(progress.plan, plan.operation, control)
        prefix = ConstructionProgress(plan=progress.plan)
        for event in progress.events:
            control.checkpoint()
            self.original.event(prefix, event, plan.operation, control)
            prefix = append_construction_event(prefix, event, prefix.revision)
        if prefix != progress:
            raise EvidenceIntegrityError(
                "Reviewed construction lost immutable original events"
            )
        self.verify_current(progress, plan, control)
        control.checkpoint()
