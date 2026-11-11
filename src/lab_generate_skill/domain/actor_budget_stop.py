"""A proven unsent round stop; completed effects and old pending intents survive."""

from typing import Literal
from .errors import OperationStopped


class ActorRoundBudgetStopped(OperationStopped):
    def __init__(
        self,
        operation_id: str,
        round_index: int,
        stage: Literal["admission", "preparation"],
    ) -> None:
        self.round_index, self.stage = round_index, stage
        self.known_unsent = True
        super().__init__("ACTOR_ROUND_BUDGET_UNSENT", operation_id)
