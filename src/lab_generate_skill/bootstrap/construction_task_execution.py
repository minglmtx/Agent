"""Bind per-intent pure composition to the original construction attempt port.

No resource acquisition, new runner, request ledger, ID generation, or retry.
The trusted factory returns the original frozen task/deps without starting it.
The existing task entry still owns durable once semantics and physical cleanup.
"""

import os
import threading
from collections.abc import Callable
from dataclasses import replace
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    verify_ready_construction,
)
from lab_generate_skill.domain.construction import (
    AttemptIntent,
    ConstructionAttemptResult,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.ports.construction import ConstructionSourceProof
from lab_generate_skill.ports.lifecycle import OperationControl
from .task_execution import RecordedConstructionTask
from .construction_actor_configuration import verify_selected_construction_factory

TaskFactory = Callable[
    [AttemptIntent, OperationContext, OperationControl], RecordedConstructionTask
]


class ConstructionTaskFactoryUnconfirmed(RuntimeError):
    def __init__(
        self,
        intent: AttemptIntent,
        operation: OperationContext,
        phase: str,
        primary: BaseException,
        task: RecordedConstructionTask | None,
    ) -> None:
        self.intent, self.operation, self.phase, self.primary, self.task = (
            intent,
            operation,
            phase,
            primary,
            task,
        )
        self.known_task_result = getattr(primary, "known_task_result", None)
        super().__init__(
            "Original construction task unresolved; retain original facts, never repeat this intent"
        )


class RecordedConstructionTasks:
    def __init__(
        self,
        construction: ConstructionDeps,
        read_operation: OperationContext,
        source: ConstructionSourceProof,
        factory: TaskFactory,
    ) -> None:
        if (
            not isinstance(construction, ConstructionDeps)
            or construction.readiness is None
            or construction.evidence is None
        ):
            raise ValueError(
                "Original construction readiness/journals/CAS are mandatory"
            )
        if not callable(getattr(source, "verify_source", None)) or not callable(
            factory
        ):
            raise ValueError(
                "Original full source proof and explicit pure task factory required"
            )
        self.construction = construction
        self.read_operation = OperationContext.model_validate(read_operation)
        if (
            self.read_operation.attempt_id,
            self.read_operation.allocation_id,
            self.read_operation.recovery_ref,
            self.read_operation.mode,
        ) != (None, None, None, "execute"):
            raise OwnershipConflict("Original run-level read operation required")
        self.source, self.factory = source, factory
        self.owner = os.getpid(), threading.get_ident()
        # Owner-local retained objects only, not a dispatch/recovery ledger.
        # Across restarts construct_targets awaits its original pending attempt;
        # execute_task additionally refuses every registered original attempt.
        self.tasks: dict[str, RecordedConstructionTask | None] = {}

    def _source(
        self, intent: AttemptIntent, control: OperationControl
    ) -> tuple[ConstructionProgress, RunSnapshot]:
        d, op = self.construction, self.read_operation
        ready = d.readiness
        assert ready is not None
        progress = ConstructionProgress.model_validate(self.source.verify_source(op))
        snapshot = RunSnapshot.model_validate(ready.runs.read(op))
        if (
            d.journal.read(op) != progress
            or progress.plan.run != intent.binding.run
            or progress.project().pending_attempt != intent
        ):
            raise OwnershipConflict(
                "Factory must retain the exact original pending source/intent"
            )
        if any(
            a.binding.attempt_id == intent.binding.attempt_id
            for a in snapshot.project()[1]
        ):
            raise DispatchAlreadyCommitted(
                "Original attempt already registered; never rebuild or redispatch"
            )
        verify_ready_construction(progress, d, op, control)
        return progress, snapshot

    def execute(
        self, intent: AttemptIntent, operation: OperationContext
    ) -> ConstructionAttemptResult:
        intent = AttemptIntent.model_validate(intent)
        operation = OperationContext.model_validate(operation)
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Construction factory changed original controller")
        run = intent.binding.run
        if (
            operation.run_id,
            operation.owner_id,
            operation.attempt_id,
            operation.allocation_id,
            operation.recovery_ref,
            operation.mode,
        ) != (
            run.owner.run_id,
            run.owner.owner_id,
            intent.binding.attempt_id,
            None,
            None,
            "execute",
        ) or (
            self.read_operation.run_id,
            self.read_operation.owner_id,
        ) != (
            run.owner.run_id,
            run.owner.owner_id,
        ):
            raise OwnershipConflict(
                "Construction factory changed original task invocation scope"
            )
        key = intent.binding.attempt_id
        if key in self.tasks:
            raise DispatchAlreadyCommitted(
                "Original task factory already invoked; no replacement after unknown"
            )
        control = self.construction.controls.bind(operation)
        control.checkpoint()
        phase = "original_source"
        task: RecordedConstructionTask | None = None
        try:
            original, snapshot = self._source(intent, control)
            phase = "pure_factory"
            self.tasks[key] = None
            task = self.factory(intent, operation, control)
            if not isinstance(task, RecordedConstructionTask):
                raise TypeError(
                    "Factory must return the original RecordedConstructionTask"
                )
            self.tasks[key] = task
            ready = self.construction.readiness
            assert ready is not None
            if (
                task.plan.intent != intent
                or task.plan.operation != operation
                or task.plan.read_operation != self.read_operation
                or task.deps.construction is not self.construction.journal
                or task.deps.runs is not ready.runs
                or task.deps.admission.construction is not self.construction.journal
                or task.deps.admission.runs is not ready.runs
                or task.deps.admission.claims is not ready.claims
                or task.deps.controls is not self.construction.controls
                or task.deps.evidence is not self.construction.evidence
            ):
                raise OwnershipConflict(
                    "Factory replaced original frozen task/journals/claims/CAS/controls"
                )
            after, after_snapshot = self._source(intent, control)
            if (after, after_snapshot) != (original, snapshot):
                raise RevisionConflict(
                    "Pure task factory changed original construction/run history"
                )
            phase = "original_task"
            control.checkpoint()
            verify_selected_construction_factory(
                original.plan, task.plan, task.deps.actors, task.deps.evidence, control
            )
            return ConstructionAttemptResult.model_validate(
                task.execute(intent, operation)
            )
        except BaseException as error:
            raise ConstructionTaskFactoryUnconfirmed(
                intent, operation, phase, error, task
            ) from error


def construction_task_dependencies(
    construction: ConstructionDeps,
    read_operation: OperationContext,
    source: ConstructionSourceProof,
    factory: TaskFactory,
) -> ConstructionDeps:
    """Use the same construct_targets entry with mandatory explicit task factory."""
    return replace(
        construction,
        attempts=RecordedConstructionTasks(
            construction, read_operation, source, factory
        ),
    )
