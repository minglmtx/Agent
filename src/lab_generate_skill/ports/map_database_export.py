"""Owned complete native output files below the original supervised worker."""

from typing import Protocol
from lab_generate_skill.domain.map_database_export import MapDatabaseExport
from .lifecycle import OperationControl


class MapDatabaseExportFiles(Protocol):
    def prepare(
        self, plan: MapDatabaseExport, program: bytes, control: OperationControl
    ) -> None:
        """Reserve fresh per-label directory/intent/program; preserve partial effects.

        Original acquired resource and admitted evidence scope precede this leaf.
        Never overwrite, reuse, clean a partial label, or execute a supplied file.
        """
        ...

    def read(self, plan: MapDatabaseExport, control: OperationControl) -> bytes:
        """After successful original command only, read complete closed native bytes.

        Check original intent/program, exact private directory members and full
        file identity; no truncation or JSON repair. Partial/missing output stays
        diagnostic. Native semantic validation and evidence retention are separate.
        """
        ...
