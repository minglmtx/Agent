"""One producer's persisted preparation declarations, without current rights."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from .lifecycle import OperationControl


@dataclass(frozen=True)
class PreparationDeclarationFacts:
    declaration: SiteTaskPreparationPlan
    site: SiteResourceSpec
    reset: ResetPlan
    binding: TaskBinding


class PreparationDeclarationInputs(Protocol):
    @property
    def declaration(self) -> SiteTaskPreparationPlan: ...
    def lookup(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> PreparationDeclarationFacts | None: ...
    def record(
        self,
        plan: TaskExecutionPlan,
        facts: PreparationDeclarationFacts,
        operation: OperationContext,
        control: OperationControl,
    ) -> None: ...
    def require(
        self,
        plan: TaskExecutionPlan,
        declaration: SiteTaskPreparationPlan,
        operation: OperationContext,
        control: OperationControl,
    ) -> PreparationDeclarationFacts: ...
    def clear(self) -> None: ...


@runtime_checkable
class PreparationDeclarationAuthority(Protocol):
    def use_preparation_inputs(self, inputs: PreparationDeclarationInputs) -> None: ...
