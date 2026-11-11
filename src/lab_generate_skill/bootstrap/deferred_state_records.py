"""Bind existing pure record/check producers after original site acquisition."""

from collections.abc import Callable
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import PreparedTask, EnvironmentBaseline
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparedPublication,
)
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
    QualifiedResetChecks,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.state_qualification import StateQualificationChecks


class DeferredPreparationRecords:
    def __init__(self, factory: Callable[[], PreparationRecords]) -> None:
        self.factory, self.attempted = factory, False
        self.value: PreparationRecords | None = None

    def original(self) -> PreparationRecords:
        if not self.attempted:
            self.attempted = True
            self.value = self.factory()
        if self.value is None:
            raise OwnershipConflict("Original preparation record binding failed")
        return self.value

    def publish(
        self, selection: PreparationSelection, op: OperationContext
    ) -> PreparedPublication:
        return self.original().publish(selection, op)

    def load(
        self, publication: PreparedPublication, op: OperationContext
    ) -> PreparedTask:
        return self.original().load(publication, op)


class DeferredStateQualificationChecks:
    def __init__(self, factory: Callable[[], StateQualificationChecks]) -> None:
        self.factory, self.attempted = factory, False
        self.value: StateQualificationChecks | None = None

    def original(self) -> StateQualificationChecks:
        if not self.attempted:
            self.attempted = True
            self.value = self.factory()
        if self.value is None:
            raise OwnershipConflict("Original state qualification binding failed")
        return self.value

    def environment(
        self,
        selection: EnvironmentSelection,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> EnvironmentBaseline:
        return self.original().environment(selection, reference, operation, control)

    def reset(
        self,
        selection: ResetSelection,
        reference: EvidenceRef,
        control: OperationControl,
    ) -> QualifiedResetChecks:
        return self.original().reset(selection, reference, control)
