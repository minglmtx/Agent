"""Single-source phase proof uses original actor-only records, never construction."""

import hashlib, json
import os
import threading
from lab_generate_skill.domain.execution_task_source import (
    ExecutionSourceFacts,
    ClaimedExecutionSourceFacts,
)
from lab_generate_skill.domain.claims import SourceClaimReceipt
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.ports.execution_task import (
    ExecutionTaskSources,
    ExecutionTaskAuthority,
    ExecutionTaskSourceRechecks,
)
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseResourceRead,
    TaskPhaseSources,
    TaskPhaseRunRead,
)
from lab_generate_skill.ports.lifecycle import OperationControl


class ExecutionTaskPhaseSources:
    def __init__(self, source: ExecutionTaskSources) -> None:
        if source is None:
            raise ValueError("Original single execution source reader required")
        self.source = source

    def view(
        self, plan: TaskExecutionPlan, facts: ExecutionSourceFacts
    ) -> TaskPhaseSourceState:
        if plan.intent != facts.source.intent:
            raise OwnershipConflict("Single phase source changed exact intent")
        raw = json.dumps(
            [
                value.model_dump_json()
                for value in (
                    facts.source,
                    facts.inputs,
                    facts.run,
                    facts.policy,
                    facts.context,
                )
            ],
            separators=(",", ":"),
        ).encode()
        return TaskPhaseSourceState(
            intent=plan.intent,
            task=facts.source.task,
            public_context_ref=facts.source.intent.public_context_ref,
            context_receipt_ref=facts.source.source_context_receipt_ref,
            source_sha256=hashlib.sha256(raw).hexdigest(),
        )

    def read(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskPhaseSourceState:
        return self.view(plan, self.source.load(plan, operation, control))

    def read_with_run(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[TaskPhaseSourceState, RunPlan]:
        facts = self.source.load(plan, operation, control)
        return self.view(plan, facts), facts.run

    def verify_run(
        self,
        plan: TaskExecutionPlan,
        state: TaskPhaseSourceState,
        run: RunPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        facts = self.source.load(plan, operation, control)
        if self.view(plan, facts) != state:
            raise RevisionConflict("Original single source changed")
        if facts.run != run:
            raise OwnershipConflict("Phase changed full original execution RunPlan")

    def read_ownership(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> tuple[TaskPhaseSourceState, RunPlan, SourceClaimReceipt] | None:
        facts = self.source.load(plan, operation, control)
        if not isinstance(facts, ClaimedExecutionSourceFacts):
            return None
        return self.view(plan, facts), facts.run, facts.claim

    def open_run_read(
        self,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> TaskPhaseRunRead:
        facts = self.source.load(plan, operation, control)
        return _ExecutionRunRead(self, plan, operation, facts)


class _ExecutionRunRead:
    """One cleanup admission's full facts; two fresh current-rights checks."""

    def __init__(
        self,
        sources: ExecutionTaskPhaseSources,
        plan: TaskExecutionPlan,
        operation: OperationContext,
        facts: ExecutionSourceFacts,
    ) -> None:
        self.sources, self.plan, self.operation = sources, plan, operation
        self._state = sources.view(plan, facts)
        self._facts: ExecutionSourceFacts | None = facts
        self._owner = os.getpid(), threading.get_ident()
        self._checks = 0

    def _original(self) -> ExecutionSourceFacts:
        if self._facts is None or self._owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Run/source bodies left their original admission")
        return self._facts

    @property
    def state(self) -> TaskPhaseSourceState:
        self._original()
        return self._state

    @property
    def run(self) -> RunPlan:
        return self._original().run

    @property
    def claim(self) -> SourceClaimReceipt | None:
        facts = self._original()
        return facts.claim if isinstance(facts, ClaimedExecutionSourceFacts) else None

    def recheck(self, control: OperationControl) -> TaskPhaseSourceState:
        facts = self._original()
        control.checkpoint()
        if self._checks >= 2:
            raise OwnershipConflict("Run/source admission already consumed")
        self._checks += 1
        source = self.sources.source
        if isinstance(source, ExecutionTaskSourceRechecks):
            source.recheck(self.plan, facts, self.operation, control)
        elif source.load(self.plan, self.operation, control) != facts:
            raise RevisionConflict("Original cleanup source facts changed")
        control.checkpoint()
        return self.state

    def close(self) -> None:
        self._facts = None


class ExecutionTaskPhaseResources:
    def __init__(
        self, sources: ExecutionTaskPhaseSources, authority: ExecutionTaskAuthority
    ) -> None:
        if sources is None or authority is None:
            raise ValueError("Original single source/resource authority required")
        self.sources, self.authority = sources, authority

    def read_for_admission(
        self,
        plan: TaskExecutionPlan,
        read: OperationContext,
        control: OperationControl,
        *,
        sources: TaskPhaseSources,
    ) -> TaskPhaseResourceRead:
        if sources is not self.sources:
            raise OwnershipConflict("Resource handoff changed original source reader")
        facts = self.sources.source.load(plan, read, control)
        return _ExecutionResourceRead(self, plan, read, facts)

    def verify(
        self,
        plan: TaskExecutionPlan,
        state: TaskPhaseSourceState,
        snapshot: RunSnapshot,
        reset: ResetPlan,
        read: OperationContext,
        control: OperationControl,
    ) -> None:
        facts = self.sources.source.load(plan, read, control)
        if self.sources.view(plan, facts) != state:
            raise RevisionConflict("Single source changed before resource check")
        self.authority.verify(plan, facts, snapshot, reset, control)


class _ExecutionResourceRead:
    """One synchronous handoff; dynamic rights and return checks stay fresh."""

    def __init__(
        self,
        resources: ExecutionTaskPhaseResources,
        plan: TaskExecutionPlan,
        read: OperationContext,
        facts: ExecutionSourceFacts,
    ) -> None:
        self.resources, self.plan, self.read = resources, plan, read
        self._state = resources.sources.view(plan, facts)
        self._facts: ExecutionSourceFacts | None = facts
        self._owner = os.getpid(), threading.get_ident()
        self._used = False
        self._verified = False
        self._rechecked = False

    @property
    def state(self) -> TaskPhaseSourceState:
        if self._facts is None or self._owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Source handoff left its original admission")
        return self._state

    def verify(
        self, snapshot: RunSnapshot, reset: ResetPlan, control: OperationControl
    ) -> None:
        control.checkpoint()
        if self._used or self._facts is None:
            raise OwnershipConflict("Source handoff is closed or already consumed")
        state = self.state
        self._used = True
        source = self.resources.sources.source
        facts = self._facts
        if isinstance(source, ExecutionTaskSourceRechecks):
            source.recheck(self.plan, facts, self.read, control)
        else:
            # Unadapted consumers retain the original complete read.
            current = source.load(self.plan, self.read, control)
            if current != facts:
                raise RevisionConflict("Single source changed before resource check")
        if self.resources.sources.view(self.plan, facts) != state:
            raise RevisionConflict("Single source changed before resource check")
        self.resources.authority.verify(self.plan, facts, snapshot, reset, control)
        control.checkpoint()
        self._verified = True

    def close(self) -> None:
        self._facts = None

    def recheck(self, control: OperationControl) -> TaskPhaseSourceState:
        """The same call's immutable graph; current claim/store/controller anew."""
        control.checkpoint()
        state = self.state
        if not self._verified or self._rechecked or self._facts is None:
            raise OwnershipConflict(
                "Source return check requires one verified admission"
            )
        self._rechecked = True
        source = self.resources.sources.source
        if isinstance(source, ExecutionTaskSourceRechecks):
            source.recheck(self.plan, self._facts, self.read, control)
        elif source.load(self.plan, self.read, control) != self._facts:
            raise RevisionConflict("Single source changed at admission return")
        control.checkpoint()
        return state


from lab_generate_skill.ports.lifecycle import OperationControls


class ExecutionTaskOriginSource:
    """Reverify original single source/claim/context for the existing origin adapter."""

    def __init__(
        self,
        plan: TaskExecutionPlan,
        sources: ExecutionTaskPhaseSources,
        controls: OperationControls,
    ) -> None:
        if sources is None or controls is None:
            raise ValueError("Original single source and controls mandatory")
        self.plan, self.sources, self.controls = (
            TaskExecutionPlan.model_validate(plan),
            sources,
            controls,
        )

    def verify_source(self, operation: OperationContext) -> TaskPhaseSourceState:
        return self.sources.read(self.plan, operation, self.controls.bind(operation))

    def verify_source_context(
        self, operation: OperationContext
    ) -> tuple[TaskPhaseSourceState, StateScope]:
        facts = self.sources.source.load(
            self.plan, operation, self.controls.bind(operation)
        )
        return self.sources.view(self.plan, facts), facts.context.scope
