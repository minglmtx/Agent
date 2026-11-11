"""Explicit unit writer/source permission for the actual current task producer.

Legacy unit_closed facts retain their own authority. This premise consumes the
original full reader, stage journal/state records and complete site ending; it
does not grant production source permission or turn software into live results.
"""

from lab_generate_skill.application.task_execution_evidence import (
    TaskExecutionEvidenceDeps,
    read_original_task_execution,
)
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.sites.retained_closure import original_closed_site
from lab_generate_skill.domain.construction import (
    AttemptCompleted,
    AttemptResolved,
    ProgressEvent,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.contexts import ContextRecords
from construction_storage_fixtures import UnitConstructionAuthority


class UnitCurrentTaskConstructionAuthority(UnitConstructionAuthority):
    reads: TaskExecutionEvidenceDeps | None = None
    site: RetainedSiteResource | None = None
    contexts: ContextRecords | None = None

    def verify_event(
        self, progress: ConstructionProgress, event: ProgressEvent, op: OperationContext
    ) -> None:
        if not isinstance(event, (AttemptCompleted, AttemptResolved)):
            super().verify_event(progress, event, op)
            return
        self.verify_plan(progress.plan, op)
        if self.reads is None or self.site is None or self.contexts is None:
            raise OwnershipConflict(
                "Original current task/closure/state unit bindings required"
            )
        control = self.site.controls.bind(op)
        actual = read_original_task_execution(
            event.result, self.reads, op, control=control
        )
        equivalent = self.contexts.load_equivalence(actual.executed.equivalence_ref, op)
        if (
            actual.plan.intent != event.result.intent
            or actual.plan.intent.binding.run != progress.plan.run
            or actual.plan.intent.binding.task != progress.plan.task.identity
            or actual.plan.intent.binding.claim_ref != progress.plan.claim_ref
            or actual.plan.intent.public_context_ref != progress.plan.public_context_ref
            or equivalent.status != "equivalent"
            or equivalent.source_context_receipt_ref
            != progress.plan.context_receipt_ref
            or equivalent.candidate_baseline_ref != actual.executed.baseline_ref
            or self.site.phase != "closed"
            or self.site.closed is None
        ):
            raise OwnershipConflict(
                "Current construction result changed original source/task/closed resource"
            )
        read = self.site.operation.cleanup(
            "unit-current-construction-site-close-read",
            now=self.site.clock.utcnow(),
            seconds=30,
        )
        original = original_closed_site(
            self.site.spec,
            self.site.operation,
            read,
            self.site.journal,
            self.site.evidence,
            self.site.controls.bind(read),
        )
        if original != self.site.closed:
            raise OwnershipConflict(
                "Original site ending changed after task completion"
            )
