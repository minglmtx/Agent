"""State evidence semantics and mandatory provenance/physical-order authority."""

from typing import Literal, Protocol
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
    QualifiedResetChecks,
)
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.reset import ResetInputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_scope import StateScope
from .lifecycle import OperationControl


class StateQualificationChecks(Protocol):
    def environment(
        self,
        selection: EnvironmentSelection,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> EnvironmentBaseline: ...
    def reset(
        self,
        selection: ResetSelection,
        reference: EvidenceRef,
        control: OperationControl,
    ) -> QualifiedResetChecks: ...


class StateQualificationAuthority(Protocol):
    def verify(
        self,
        scope: StateScope,
        selection_ref: EvidenceRef,
        phase: Literal["environment", "reset"],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Read actual facts; verify source, original worker/site, policy and order.

        Require no competing writer, completed original browser closure before
        restore, retained lease, supported complete task effects and original
        immutable publication. No authority from filenames or synthetic facts.
        """
        ...


class EnvironmentQualifications(Protocol):
    """Existing environment publication/read interface; no task effects."""

    def publish_environment(
        self, selection_ref: EvidenceRef, operation: OperationContext
    ) -> EvidenceRef: ...

    def load_environment(
        self,
        selection_ref: EvidenceRef,
        reference: EvidenceRef,
        operation: OperationContext,
    ) -> EnvironmentBaseline: ...


class ResetQualifications(Protocol):
    """Existing complete reset qualification operation; no new recovery driver."""

    def publish_reset_facts(
        self, selection_ref: EvidenceRef, operation: OperationContext
    ) -> ResetInputs: ...
