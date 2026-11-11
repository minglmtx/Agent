"""Frozen browser worker inputs, bounded process-event facts and returned state.

No browser handles, private task specifications or inferred task success. The
current engine supports header-level response capture and action boundaries;
body/download/custom evidence requires its explicit collector before admission.
"""

from typing import Literal, Self
from pydantic import Field, model_validator
from .evidence import EvidenceRequirements
from .browser import BrowserAction
from .lifecycle import OperationContext
from .observation import Observation
from .state_scope import StateScope
from .task import PublicTask
from .validation import Contract, Identifier, NonEmptyText


class BrowserSessionSpec(Contract):
    schema_version: Literal["browser-session-spec/1"] = "browser-session-spec/1"
    scope: StateScope
    task: PublicTask
    chromium_executable: NonEmptyText
    seed: int = Field(ge=0, le=2**32 - 1)
    action_timeout_ms: int = Field(ge=500, le=10000)
    requirements: EvidenceRequirements
    max_events: int = Field(ge=4, le=4096)

    @model_validator(mode="after")
    def admitted_surface(self) -> Self:
        if self.scope.task != self.task.identity:
            raise ValueError("Browser task must belong to the original scope")
        if not self.chromium_executable.startswith("/"):
            raise ValueError(
                "Browser executable must be an explicitly pinned absolute path"
            )
        if self.requirements.facts or "download" in self.requirements.events:
            raise ValueError(
                "This engine requires an additional collector for custom facts/downloads"
            )
        return self


class BrowserRuntimeEvent(Contract):
    sequence: int = Field(ge=0)
    kind: Literal[
        "before_navigation", "response", "before_action", "after_action", "terminal"
    ]
    action_id: Identifier | None = None
    url: str | None = None
    status: int | None = Field(default=None, ge=0, le=599)


class BrowserReadout(Contract):
    schema_version: Literal["browser-initial-return/1", "browser-step-return/1"] = (
        "browser-step-return/1"
    )
    scope: StateScope
    operation: OperationContext
    action: BrowserAction | None
    observation: Observation
    events: tuple[BrowserRuntimeEvent, ...]
    environment_reward: float = Field(allow_inf_nan=False)
    terminated: bool
    truncated: bool
    protocol_terminal: bool

    @model_validator(mode="after")
    def original_return(self) -> Self:
        if (
            self.observation.task,
            self.observation.attempt_id,
            self.observation.context_id,
        ) != (self.scope.task, self.scope.attempt_id, self.scope.context_id):
            raise ValueError("Browser readout changed original observation scope")
        if (
            self.operation.run_id,
            self.operation.owner_id,
            self.operation.attempt_id,
            self.operation.mode,
        ) != (
            self.scope.owner.run_id,
            self.scope.owner.owner_id,
            self.scope.attempt_id,
            "execute",
        ):
            raise ValueError("Browser readout changed original execution")
        expected = (
            "browser-initial-return/1"
            if self.action is None
            else "browser-step-return/1"
        )
        if self.schema_version != expected:
            raise ValueError("Browser return schema must match its actual phase")
        if (self.action is None) != (self.observation.sequence == 0):
            raise ValueError("Only initial readout can omit its action")
        return self
