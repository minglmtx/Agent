"""Exact terminal bodies handed from capture to judgment in one owned task."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.terminal_read import (
    TerminalReadRequest,
    TerminalReadBodies,
)
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.initial_observation import InitialObservationReads
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.terminal_reads import TerminalEvidenceReads
from .task_initialization_inputs import TaskInitializationInputs


class TaskTerminalEvidenceInputs:
    def __init__(
        self,
        plan: TaskExecutionPlan,
        scope: TaskInitializationInputs,
        proof: TerminalEvidenceReads,
        initials: InitialObservationReads,
        selected: Callable[[OperationControl], InitialObservationSelection],
    ) -> None:
        self.plan = TaskExecutionPlan.model_validate(plan)
        if (
            scope.plan != self.plan
            or not callable(selected)
            or initials is None
            or proof is None
        ):
            raise OwnershipConflict(
                "Original terminal proof/initial/body scope required"
            )
        self.scope, self.proof, self.initials, self.selected = (
            scope,
            proof,
            initials,
            selected,
        )

    def verify(
        self,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        self.scope.check(operation, control)
        initial = self.initials.load(self.selected(control), operation, control)
        request = TerminalReadRequest(
            terminal_ref=reference,
            contract=self.plan.evaluation,
            initial=initial,
            operation=operation,
        )
        old = self.scope.terminal_bodies
        if old is not None:
            if old.request != request:
                raise OwnershipConflict(
                    "Original terminal handoff cannot change or rebuild"
                )
            self.proof.check_current(control)
            return
        bodies = TerminalReadBodies.model_validate(self.proof.read(request, control))
        if bodies.request != request or bodies.purpose != "same_task":
            raise OwnershipConflict(
                "Terminal proof changed exact requested body inputs"
            )
        self.scope.check(operation, control)
        self.scope.terminal_bodies = bodies

    @contextmanager
    def inputs(
        self,
        original: EvidenceReader,
        operation: OperationContext,
        control: OperationControl,
    ) -> Iterator[EvidenceReader]:
        self.scope.check(operation, control)
        bodies = self.scope.terminal_bodies
        if bodies is None:
            raise OwnershipConflict(
                "Original verified terminal output missing; no rebuild"
            )
        initial = self.initials.load(self.selected(control), operation, control)
        if (
            bodies.request.initial != initial
            or bodies.request.contract != self.plan.evaluation
        ):
            raise OwnershipConflict(
                "Terminal handoff changed original initial/contract"
            )
        self.proof.check_current(control)
        reader = _TerminalInputReader(self.scope, bodies, original, operation)
        try:
            yield reader
            self.scope.check(operation, control)
            self.proof.check_current(control)
        finally:
            reader.close()


class _TerminalInputReader:
    def __init__(
        self,
        scope: TaskInitializationInputs,
        bodies: TerminalReadBodies,
        original: EvidenceReader,
        operation: OperationContext,
    ) -> None:
        self.scope, self.original, self.operation = scope, original, operation
        self.bodies = {
            value.reference: value.json_text.encode() for value in bodies.bodies
        }
        self.digests = {reference.sha256 for reference in self.bodies}
        self.active = True

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        self.scope.check(self.operation, control)
        if not self.active:
            raise OwnershipConflict("Terminal input reader left original consumption")
        reference = EvidenceRef.model_validate(reference)
        raw = self.bodies.get(reference)
        if raw is None:
            if reference.sha256 in self.digests:
                raise EvidenceIntegrityError("Terminal reference metadata changed")
            return self.original.read(reference, control)
        return raw

    def close(self) -> None:
        self.active = False
        self.bodies.clear()
        self.digests.clear()
