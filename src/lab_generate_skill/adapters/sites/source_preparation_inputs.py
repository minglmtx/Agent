"""Exact preparation bodies during one original source qualification call.

Uses the existing preparation/browser input ports. Every consumption checks the
original live caller, acquired resource and storage authority; no permission or
body survives close, and no old source/claim is adopted.
"""

import os
import threading
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.prepared_browser import PreparedBrowserInputs
from .source_qualification_native import SourceQualificationNativeAuthority
from .task_preparation_record_inputs import TaskPreparationRecordInputs


class SourcePreparationInputs:
    def __init__(self, native: SourceQualificationNativeAuthority) -> None:
        self.native = native
        self.identity = os.getpid(), threading.get_ident()
        self.active = True
        self.prepared_browser: PreparedBrowserInputs | None = None
        self.records = TaskPreparationRecordInputs(self, self)

    @property
    def task_identity(self) -> TaskIdentity:
        return self.native.owner.scope.task

    @property
    def preparation_scope(self) -> tuple[str, str, str | None]:
        scope = self.native.owner.scope
        return scope.owner.run_id, scope.owner.owner_id, scope.attempt_id

    def check(self, op: OperationContext, control: OperationControl) -> None:
        control.checkpoint()
        scope = self.native.owner.scope
        if (
            not self.active
            or self.identity != (os.getpid(), threading.get_ident())
            or (op.run_id, op.owner_id, op.attempt_id)
            != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id)
        ):
            raise OwnershipConflict(
                "Source preparation bodies left original invocation"
            )

    def check_context_current(
        self, op: OperationContext, control: OperationControl
    ) -> None:
        self.check(op, control)
        self.native.require_acquired(op, control)
        self.check(op, control)

    def close(self) -> None:
        self.active = False
        self.records.clear()
        self.prepared_browser = None
