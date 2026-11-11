"""One readonly invocation of the existing pure state-qualification contract."""

from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .evidence_read_scope import EvidenceReadScope
from .identity import TaskIdentity
from .lifecycle import OperationContext
from .state_qualification import EnvironmentSelection, ResetSelection
from .state_scope import private_state_ref


class StateReadCommand(Contract):
    schema_version: Literal["state-read-command/1"] = "state-read-command/1"
    scope: EvidenceReadScope
    workspace_root: str = Field(min_length=1, max_length=4096)
    task: TaskIdentity
    selection: Annotated[
        EnvironmentSelection | ResetSelection, Field(discriminator="schema_version")
    ]
    selection_ref: EvidenceRef
    operation: OperationContext | None

    @model_validator(mode="after")
    def supported(self) -> Self:
        path = PurePosixPath(self.workspace_root)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("Original absolute workspace required")
        if (
            self.task.site,
            self.task.family,
            self.task.contract_version,
            self.task.split,
        ) not in {
            ("shopping_admin", "page_navigation", 1, "train"),
            ("gitlab", "group_creation", 1, "train"),
        }:
            raise ValueError("Explicit compiled pure state-check binding required")
        private_state_ref(self.selection_ref, self.selection.schema_version)
        if isinstance(self.selection, EnvironmentSelection):
            op = self.operation
            scope = self.selection.scope
            if (
                scope.task != self.task
                or op is None
                or (op.run_id, op.owner_id, op.attempt_id)
                != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id)
            ):
                raise ValueError("Environment proof changed original task/operation")
        elif self.operation is not None:
            raise ValueError("Reset proof derives its original operation from evidence")
        return self
