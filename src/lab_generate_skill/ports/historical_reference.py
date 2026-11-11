"""Historical bytes only; no path rewriting, execution, migration or fallback."""

from typing import Protocol
from lab_generate_skill.domain.historical_reference import HistoricalKey
from .lifecycle import OperationControl


class HistoricalReader(Protocol):
    def read(self, key: HistoricalKey, control: OperationControl) -> bytes: ...
