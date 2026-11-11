"""Construction candidate lifecycle, composed over the existing ActorRunner.

The existing task lifecycle owns initialize/equivalence/capture/judgment/finally
restore/close and durable attempt registration. This port is not an alternative
Actor runner. Invoke only for a newly registered original AttemptIntent; never
reexecute pending/unknown attempts, even after exceptions or acknowledgement loss.
"""

from typing import Protocol
from lab_generate_skill.domain.construction import (
    AttemptIntent,
    ConstructionAttemptResult,
)
from lab_generate_skill.domain.lifecycle import OperationContext


class ConstructionAttemptExecution(Protocol):
    def execute(
        self, intent: AttemptIntent, operation: OperationContext
    ) -> ConstructionAttemptResult:
        """Return original saved judgment/closure facts, no manufactured failures."""
        ...
