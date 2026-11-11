"""Actual cleanup permission and independently proven non-start, never defaults."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_finalization import (
    TaskFinalizationPlan,
    UnstartedTaskBrowser,
)
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.reset import ResetReceipt
from .lifecycle import OperationControl


class TaskFinalizationAuthority(Protocol):
    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        references: tuple[EvidenceRef, ...],
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Original claim/frozen run/resources/source/worker/lease and once native
        request references. Cleanup remains permitted after execution cancellation
        only while original exclusive ownership and cleanup budget are valid.
        Never grant another attempt, prepare, restore or resume by changing IDs.
        """
        ...


@runtime_checkable
class TaskFinalizationDeclarationInputs(Protocol):
    def read_finalization_declaration(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> bytes:
        """Exact immutable declarations within the original owned task invocation.

        This supplies bytes only. Current source, claim, run, storage and physical
        permissions remain mandatory in verify; no native result or permission
        may be retained here. Unsupported suppliers use original evidence reads.
        """
        ...


@runtime_checkable
class RestoredTaskResetReader(Protocol):
    def load_restored_reset(
        self,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> ResetReceipt:
        """Consume this invocation's exact published body, with fresh state authority.

        This cannot restore/resume or renew an expired cleanup allowance.
        """
        ...


class UnstartedTaskBrowserAuthority(Protocol):
    def close_unstarted(
        self,
        plan: TaskExecutionPlan,
        declaration: TaskFinalizationPlan,
        observed: UnstartedTaskBrowser,
        observed_ref: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        """Independently prove original exclusive controller, no registration or
        committed acquisition/dispatch and no resource ever started. Missing data
        or a lost start acknowledgement is not this proof. Return unconfirmed or
        raise if physical non-start cannot actually be established.
        """
        ...
