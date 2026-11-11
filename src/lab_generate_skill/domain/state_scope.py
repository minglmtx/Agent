"""Identity and reference boundaries shared by initial/reset state facts."""

from typing import ClassVar, Literal, Self
from pydantic import model_validator
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .identity import TaskIdentity
from .lifecycle import ResourceOwner, OperationContext
from .validation import Contract, Identifier


def private_state_ref(ref: EvidenceRef, schema: str) -> None:
    if ref.visibility != "private" or ref.content_schema != schema:
        raise ValueError("Expected private " + schema)


class StateScope(Contract):
    schema_version: Literal["state-scope/1"] = "state-scope/1"
    owner: ResourceOwner
    task: TaskIdentity
    attempt_id: Identifier
    context_id: Identifier


class StateFact(Contract):
    """Recorded operation; deadline is historical, never extended on read."""

    operation_mode: ClassVar[Literal["execute", "cleanup"]] = "execute"
    scope: StateScope
    operation: OperationContext

    @model_validator(mode="after")
    def same_attempt(self) -> Self:
        if (
            self.operation.run_id,
            self.operation.owner_id,
            self.operation.attempt_id,
            self.operation.mode,
        ) != (
            self.scope.owner.run_id,
            self.scope.owner.owner_id,
            self.scope.attempt_id,
            self.operation_mode,
        ):
            raise OwnershipConflict(
                "State fact must retain its run/owner/attempt and phase"
            )
        return self


class StateCommitUnconfirmed(RuntimeError):
    """Known summary reference survives a final checkpoint failure; never restore again."""

    reason_code = "STATE_COMMIT_UNCONFIRMED"

    def __init__(self, reference: EvidenceRef) -> None:
        self.reference = reference
        super().__init__(
            "State summary persisted; reconcile exact facts without physical actions"
        )
