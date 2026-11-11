"""Mandatory current construction/source admission for preparation effects."""

from typing import Protocol
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl


class TaskPreparationAuthority(Protocol):
    def verify(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Original pending attempt, claim, held live site, freshness/exclusivity.

        Reconciliation is read-only provenance, never another native task call.
        Metadata shape, returned references or an engineering authority alone do
        not qualify a formal source. No default implementation is permitted.
        """
        ...
