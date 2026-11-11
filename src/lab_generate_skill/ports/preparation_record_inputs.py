"""Optional immutable preparation bodies inside one original task invocation."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.preparation_record import (
    PreparationInputs,
    PreparationSelection,
    PreparedPublication,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.identity import TaskIdentity


class PreparationRecordScope(Protocol):
    @property
    def task_identity(self) -> TaskIdentity: ...
    @property
    def preparation_scope(self) -> tuple[str, str, str | None]: ...
    def check(self, op: OperationContext, control: OperationControl) -> None: ...


@dataclass(frozen=True)
class LoadedPreparation:
    inputs: PreparationInputs
    verified: frozenset[EvidenceRef]
    private_spec: bytes | None = field(repr=False)
    snapshot: bytes | None = field(repr=False)


class PreparationRecordInputReads(Protocol):
    def preparation_inputs(
        self,
        selection: PreparationSelection,
        op: OperationContext,
        control: OperationControl,
        read: Callable[[], LoadedPreparation],
    ) -> LoadedPreparation: ...

    def publication_inputs(
        self,
        publication: PreparedPublication,
        op: OperationContext,
        control: OperationControl,
        read: Callable[[], tuple[bytes, bytes]],
    ) -> tuple[bytes, bytes]: ...

    def clear(self) -> None: ...


@runtime_checkable
class PreparationCheckInputReads(Protocol):
    def preparation_checks(
        self,
        inputs: PreparationInputs,
        checker: object,
        op: OperationContext,
        control: OperationControl,
        check: Callable[[], StateChecks],
    ) -> StateChecks:
        """Same-call pure checks of exact immutable inputs; no authority verdict."""
        ...
