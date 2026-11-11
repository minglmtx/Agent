"""Bind terminal IO to the same real supervised source namespace/admission."""

from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedExecutionTaskSourceChecks,
)
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.adapters.plans.terminal_read_transport import (
    SupervisedTerminalReads,
)
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.terminal_reads import TerminalEvidenceReads
from lab_generate_skill.domain.terminal_read import (
    TerminalReadRequest,
    TerminalReadBodies,
)
from .terminal_read_bindings import require_complete_terminal_bodies


class CompleteTerminalReads:
    """Expose a proof only after its complete original dependency set is checked."""

    def __init__(self, original: TerminalEvidenceReads) -> None:
        self.original = original

    def read(
        self, request: TerminalReadRequest, control: OperationControl
    ) -> TerminalReadBodies:
        bodies = TerminalReadBodies.model_validate(self.original.read(request, control))
        if bodies.request != request or bodies.purpose != "same_task":
            raise OwnershipConflict("Terminal proof changed original request/purpose")
        require_complete_terminal_bodies(bodies, control)
        self.original.check_current(control)
        return bodies

    def check_current(self, control: OperationControl) -> None:
        self.original.check_current(control)


def owned_terminal_reads(
    source: OriginalExecutionTaskSource,
    evidence: EvidenceStore,
    plan: TaskExecutionPlan,
) -> TerminalEvidenceReads | None:
    # Direct local evidence readers do not incur supervised per-leaf exchanges.
    # They retain their original read path. A supervised production namespace
    # must supply its actual original source transport; it cannot fall back.
    if not isinstance(evidence, ManagedEvidenceStore):
        return None
    checks = source.source_checks
    if not isinstance(checks, SupervisedExecutionTaskSourceChecks):
        raise TypeError("Supervised owned terminal requires original source checks")
    original = checks.transport
    if original.store is not evidence:
        raise OwnershipConflict("Terminal binding changed original metadata store")
    checks.require_current(plan.operation, checks.owner.controls.bind(plan.operation))
    return CompleteTerminalReads(
        SupervisedTerminalReads(
            original.scope, evidence, original.admission, plan.intent.binding.task
        )
    )
