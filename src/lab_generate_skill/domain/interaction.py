"""Link a generated action to its actual return, non-dispatch or uncertainty."""

from typing import Literal, Self
from pydantic import model_validator
from .browser import BrowserAction, StepResult, observation_reference
from .errors import OwnershipConflict
from .evidence import EvidenceRef
from .state_scope import StateFact, private_state_ref
from .validation import Identifier


class InteractionEvent(StateFact):
    schema_version: Literal["interaction-event/1"] = "interaction-event/1"
    generation_id: Identifier
    action: BrowserAction
    before_observation_ref: EvidenceRef
    outcome: Literal["returned", "returned_incomplete", "not_dispatched", "uncertain"]
    result: StepResult | None = None
    failure_ref: EvidenceRef | None = None

    @model_validator(mode="after")
    def actual_outcome(self) -> Self:
        observation_reference(self.before_observation_ref)
        if self.failure_ref is not None:
            private_state_ref(self.failure_ref, "interaction-failure/1")
        if self.outcome != "returned":
            if self.result is not None or self.failure_ref is None:
                raise ValueError(
                    "Absent/incomplete return needs diagnostic, no fabricated observation"
                )
        elif self.result is None or self.failure_ref is not None:
            raise ValueError("Returned interaction requires its actual result")
        else:
            result = self.result
            if (
                result.scope,
                result.operation,
                result.action_id,
                result.before_observation_ref,
            ) != (
                self.scope,
                self.operation,
                self.action.action_id,
                self.before_observation_ref,
            ):
                raise OwnershipConflict(
                    "Step return must match its original action and operation"
                )
        return self
