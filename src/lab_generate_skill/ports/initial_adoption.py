"""Live authority for a selected current comparison, never an old-owner grant."""

from typing import Protocol, runtime_checkable
from lab_generate_skill.domain.initial_adoption import InitialAdoptionInputs
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl


@runtime_checkable
class InitialAdoptionAuthority(Protocol):
    @property
    def inputs(self) -> InitialAdoptionInputs: ...

    def verify_adoption(
        self,
        inputs: InitialAdoptionInputs,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        """Recheck actual source/claim/caller/permission on every relevant gate.

        Current native baseline/comparison/resource authority remains separate.
        No source/initialization/model/browser producer or mutation is allowed.
        """
        ...
