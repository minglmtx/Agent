"""Read-only semantic reconstruction and required actual execution authority."""

from typing import Protocol, runtime_checkable
from dataclasses import dataclass
from lab_generate_skill.domain.preparation_record import (
    PreparationInputs,
    PreparationSelection,
    PreparedPublication,
)
from lab_generate_skill.domain.preparation import PreparedTask, PreparationReceipt
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl
from lab_generate_skill.domain.preparation_read import (
    PreparationReadRequest,
    PreparationReadBodies,
)


@runtime_checkable
class PreparationInputReads(Protocol):
    def load_preparation_inputs(
        self, request: PreparationReadRequest, control: OperationControl
    ) -> PreparationReadBodies | None:
        """One complete original graph read; never a current authority grant."""
        ...


class PreparationChecks(Protocol):
    def check(
        self, inputs: PreparationInputs, control: OperationControl
    ) -> StateChecks:
        """Recompute exact declared checks from actual private evidence; no site effects."""
        ...


@runtime_checkable
class PreparationBodyChecks(Protocol):
    def check_with_bodies(
        self,
        inputs: PreparationInputs,
        private_spec: bytes | None,
        snapshot: bytes | None,
        control: OperationControl,
    ) -> StateChecks:
        """Consume exact immutable bodies read in this call, never permission.

        Missing optional bodies use the original reader. No cross-call storage
        or change to the persisted PreparationInputs/PreparedPublication schema.
        """
        ...


class PreparationAuthority(Protocol):
    def verify(
        self,
        inputs: PreparationInputs,
        checks: StateChecks,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        """Verify original worker/result provenance, ordering, release/source/claim,
        actual environment policy and writer exclusivity. No default approval.
        Read-only cleanup reconciliation is not new execution permission.
        """
        ...


class PreparationRecords(Protocol):
    def publish(
        self, selection: PreparationSelection, op: OperationContext
    ) -> PreparedPublication: ...
    def load(
        self, publication: PreparedPublication, op: OperationContext
    ) -> PreparedTask: ...


@dataclass(frozen=True)
class LoadedPreparedTask:
    """Same-call immutable result; carries no current authority decision."""

    prepared: PreparedTask
    receipt: PreparationReceipt
    inputs: PreparationInputs


@runtime_checkable
class PreparationReceiptReads(Protocol):
    def load_with_receipt(
        self, publication: PreparedPublication, op: OperationContext
    ) -> LoadedPreparedTask: ...
