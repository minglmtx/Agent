"""Infrastructure-independent error categories for evidence port failures.

Adapters raise these without leaking credentials or raw evidence contents.
Applications preserve the original cause and handle cleanup separately.
"""


class EvidenceError(RuntimeError):
    """Evidence cannot support a judgment; never a task-failure reward."""

    reason_code = "EVIDENCE_ERROR"


class IncompleteAnswerEvidence(ValueError):
    """No complete original execution, rather than a wrong user answer."""


class EvidenceNotFound(EvidenceError):
    """The referenced bytes have not been persisted or are unavailable."""

    reason_code = "MISSING_EVIDENCE"


class EvidenceIntegrityError(EvidenceError):
    """Stored bytes, their size, or their location disagree with the reference."""

    reason_code = "EVIDENCE_INTEGRITY_MISMATCH"


class OperationStopped(RuntimeError):
    """Stop before further effects; cleanup uses a distinct operation context."""

    def __init__(self, reason_code: str, operation_id: str) -> None:
        self.reason_code = reason_code
        self.operation_id = operation_id
        super().__init__(f"{reason_code}: operation {operation_id}")


class OwnershipConflict(RuntimeError):
    """A resource/token belongs to another immutable owner or plan."""

    reason_code = "OWNERSHIP_CONFLICT"


class RevisionConflict(RuntimeError):
    """Optimistic revision is stale; caller must inspect existing facts."""

    reason_code = "REVISION_CONFLICT"


class InvalidTransition(ValueError):
    """A proposed state change violates the declared lifecycle."""

    reason_code = "INVALID_TRANSITION"


class BudgetExceeded(RuntimeError):
    """Shared authorization/subbudget is exhausted or blocked by an overage."""

    reason_code = "CONTEXT_OR_COST_LIMIT"


class DispatchAlreadyCommitted(RuntimeError):
    """Sending may already have happened; never return another send permit."""

    reason_code = "DELIVERY_ALREADY_COMMITTED"


class JournalCapacityExceeded(ValueError):
    """Stop new work; preserve bounded diagnostic closure space."""

    reason_code = "JOURNAL_CAPACITY_EXCEEDED"


class GeneratorInputBudgetExceeded(ValueError):
    """Known pre-inference token budget rejection; never a replay permission."""


class ActorInputBudgetExceeded(ValueError):
    """Actor input/output token reservation rejected before inference; no truncation."""
