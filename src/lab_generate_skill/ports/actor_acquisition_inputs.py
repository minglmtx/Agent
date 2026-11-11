"""One fresh optional proof, not a cache or a resource/dispatch permission."""

from typing import Protocol
from lab_generate_skill.domain.actor_acquisition_inputs import (
    ActorAcquisitionInputs,
    ActorAcquisitionBodies,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from .lifecycle import OperationControl


class ActorAcquisitionReads(Protocol):
    def read_original(
        self,
        selection: ActorAcquisitionInputs,
        operation: OperationContext,
        control: OperationControl,
    ) -> ActorAcquisitionBodies | None:
        """None only before effects for unsupported scope; errors never fallback."""
        ...
