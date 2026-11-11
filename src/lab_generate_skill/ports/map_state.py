"""Full persistent host files from the original private frontend clone."""

from typing import Protocol
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.map_state import MapPersistentState
from .lifecycle import OperationControl


class MapPersistentFiles(Protocol):
    def capture(
        self, spec: MapServiceSpec, control: OperationControl
    ) -> MapPersistentState:
        """Full pinned baseline and public/storage hashes; reject missing/alias/races.

        Read actual input/frontend host data, never empty bind-target placeholders.
        No mutation, truncation, resource admission or reset is permitted here.
        """
        ...
