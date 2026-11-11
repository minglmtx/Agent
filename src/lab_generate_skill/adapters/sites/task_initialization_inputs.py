"""Immutable initialization bodies within one owned task resource scope.

This object carries no permission. Consumers must still call the original live
resource, claim and storage authorities. No independent invocation can reuse it.
"""

import os
import threading
from contextlib import contextmanager
from collections.abc import Iterator
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.initial_equivalence import EquivalenceInputs
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_initialization import TaskInitialComparison
from lab_generate_skill.ports.preparation_record_inputs import (
    PreparationRecordInputReads,
)
from lab_generate_skill.ports.prepared_browser import PreparedBrowserInputs
from lab_generate_skill.ports.task_preparation_inputs import (
    PreparationDeclarationInputs,
)
from lab_generate_skill.ports.trace_body_inputs import TraceBodyInputs
from lab_generate_skill.domain.terminal_read import TerminalReadBodies


class TaskInitializationInputs:
    @property
    def task_identity(self) -> TaskIdentity:
        return self.plan.intent.binding.task

    @property
    def preparation_scope(self) -> tuple[str, str, str | None]:
        op = self.plan.operation
        return op.run_id, op.owner_id, op.attempt_id

    def __init__(self, plan: TaskExecutionPlan) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        self.owner = os.getpid(), threading.get_ident()
        self.active = False
        self.used = False
        self.preparation_records: PreparationRecordInputReads | None = None
        self.preparation_declarations: PreparationDeclarationInputs | None = None
        self.trace_inputs: TraceBodyInputs | None = None
        self.trace_input_statistics: dict[str, int] = {}
        self.prepared_browser: PreparedBrowserInputs | None = None
        self.source: (
            tuple[EvidenceRef, PublicContextReceipt, PublicContextInputs] | None
        ) = None
        self.initial: InitialObservationInputs | None = None
        self.terminal_bodies: TerminalReadBodies | None = None
        self.equivalence: (
            tuple[EvidenceRef, EquivalenceInputs, dict[EvidenceRef, bytes]] | None
        ) = None
        self.candidate_baseline: (
            tuple[BaselineInputs, BaselineReceipt, EvidenceRef] | None
        ) = None
        self.candidate_baseline_authority: object | None = None
        self.comparison: tuple[object, TaskInitialComparison] | None = None
        self.finalization: tuple[object, dict[EvidenceRef, bytes]] | None = None
        self.finalization_declarations: (
            tuple[object, dict[EvidenceRef, bytes]] | None
        ) = None
        self.browser_acquired: tuple[EvidenceRef, BrowserWorkerAcquiredFact] | None = (
            None
        )

    def check(self, op: OperationContext, control: OperationControl) -> None:
        control.checkpoint()
        p = self.plan.operation
        if (
            not self.active
            or self.owner != (os.getpid(), threading.get_ident())
            or (op.run_id, op.owner_id, op.attempt_id)
            != (p.run_id, p.owner_id, p.attempt_id)
        ):
            raise OwnershipConflict(
                "Initialization bodies left original task invocation"
            )

    @contextmanager
    def scope(self) -> Iterator[None]:
        if self.used or self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict(
                "Initialization input scope is original and one-shot"
            )
        self.used = self.active = True
        try:
            yield
        finally:
            self.active = False
            if self.trace_inputs is not None:
                self.trace_input_statistics = dict(self.trace_inputs.statistics)
                self.trace_inputs.clear()
            self.trace_inputs = None
            if self.preparation_declarations is not None:
                self.preparation_declarations.clear()
            self.preparation_declarations = None
            if self.preparation_records is not None:
                self.preparation_records.clear()
            self.preparation_records = None
            self.prepared_browser = None
            self.source = self.initial = self.equivalence = None
            self.terminal_bodies = None
            self.candidate_baseline = self.browser_acquired = None
            self.candidate_baseline_authority = None
            self.comparison = None
            if self.finalization_declarations is not None:
                self.finalization_declarations[1].clear()
            self.finalization = self.finalization_declarations = None
