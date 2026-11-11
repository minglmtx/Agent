"""Retain an actual step return inside its existing Actor result window.

This owner-local adapter grants only evidence publication after a native return.
It never changes the execution control, repeats an action, or extends the
action deadline plus the already selected result-cleanup duration.
"""

import hashlib
import os
import threading
from datetime import timedelta

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import AllocationToken, OperationContext
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControl,
    OperationControls,
)


class BrowserReturnPublication:
    def __init__(
        self,
        token: AllocationToken,
        controls: OperationControls,
        clock: Clock,
        seconds: int,
    ) -> None:
        if type(seconds) is not int or not 1 <= seconds <= 60:
            raise ValueError("Original Actor result duration must be in 1..60 seconds")
        self.token = AllocationToken.model_validate(token)
        if self.token.scope != "attempt" or self.token.resource_kind != "browser":
            raise OwnershipConflict("Original attempt browser allocation required")
        self.controls, self.clock, self.seconds = controls, clock, seconds
        self.owner = os.getpid(), threading.get_ident()
        self.used: set[str] = set()

    def bind(self, operation: OperationContext) -> OperationControl:
        operation = OperationContext.model_validate(operation)
        token = self.token
        if (
            self.owner != (os.getpid(), threading.get_ident())
            or operation.mode != "execute"
            or (operation.run_id, operation.owner_id, operation.attempt_id)
            != (token.owner.run_id, token.owner.owner_id, token.attempt_id)
            or (operation.allocation_id, operation.recovery_ref)
            != (token.allocation_id, token.recovery_ref)
            or operation.operation_id in self.used
        ):
            raise OwnershipConflict(
                "Return publication changed or repeated original action"
            )
        self.used.add(operation.operation_id)
        identity = (
            "browser-return-"
            + hashlib.sha256(operation.model_dump_json().encode()).hexdigest()
        )
        cleanup = operation.cleanup(
            identity, now=self.clock.utcnow(), seconds=self.seconds
        )
        cleanup = OperationContext.model_validate(
            cleanup.model_copy(
                update={
                    "deadline": min(
                        cleanup.deadline,
                        operation.deadline + timedelta(seconds=self.seconds),
                    )
                }
            )
        )
        bound = self.controls.bind(cleanup)
        bound.checkpoint()
        return bound
