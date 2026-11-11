"""One original read-only observation shared with the concrete resolver authority."""

from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from . import inspection
from .inspection_result import StorageObservation, StorageInspectionFailure
from lab_generate_skill.domain.evidence_io import EvidenceCommand


class ObservedStorageInspection:
    def __init__(self, command: EvidenceCommand) -> None:
        self.command = EvidenceCommand.model_validate(command)
        self.observation: StorageObservation | None = None
        self.error: BaseException | None = None
        self._attempted = False

    def inspect(
        self, command: EvidenceCommand, control: OperationControl
    ) -> StorageObservation:
        if command != self.command:
            raise OwnershipConflict("Inspection belongs to another physical command")
        if self._attempted:
            raise DispatchAlreadyCommitted(
                "Original storage inspection was already attempted"
            )
        self._attempted = True
        try:
            self.observation = inspection.inspect_exchange_storage(command, control)
            return self.observation
        except BaseException as error:
            self.error = error
            self.observation = (
                error.observation
                if isinstance(error, StorageInspectionFailure)
                else getattr(error, "storage_inspection", None)
            )
            raise
