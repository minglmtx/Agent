"""Task-definition publication diagnostics, not execution/initialization state."""

from dataclasses import dataclass
from .evidence import EvidenceRef
from .task import TaskBinding, PublicTask


@dataclass(frozen=True)
class TaskBindingInputs:
    """Immutable bodies read and authorized in one call; never a later permit."""

    binding: TaskBinding
    public_task: PublicTask
    private_spec: bytes
    baseline: bytes


class TaskBindingCommitUnconfirmed(RuntimeError):
    """A returned binding reference survived a later stop; reconcile by reading it.

    A put that raised without returning stays its original exception. This error
    never licenses task preparation, retry of actions, or a fabricated baseline.
    """

    reason_code = "TASK_BINDING_COMMIT_UNCONFIRMED"

    def __init__(self, reference: EvidenceRef) -> None:
        self.reference = reference
        super().__init__("Task binding published; final confirmation interrupted")
