"""Frozen limits for bounded run snapshots; no filesystem or execution effects.

Each entry has an encoded UTF-8 ceiling. Preflight budgets a complete normal
batch plus one uncertain submission, including JSON wrapper/comma overhead.
Every proposed snapshot must still fit all outstanding diagnostic closure
events at that ceiling. This reserves space, not disk availability or permission
to retry a submission. Large diagnostics belong in referenced evidence.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from .errors import JournalCapacityExceeded
from .validation import Contract


class JournalCapacity(Contract):
    schema_version: Literal["run-journal-capacity/1"] = "run-journal-capacity/1"
    max_attempts: int = Field(ge=0, le=900)
    max_entries: int = Field(ge=9, le=10000)
    max_bytes: int = Field(ge=1, le=8 * 1024 * 1024)
    max_entry_bytes: int = Field(ge=1, le=8 * 1024 * 1024)

    @property
    def minimum_entries(self) -> int:
        """8 normal run stages + 11 per attempt + one uncertainty observation."""
        return 9 + 11 * self.max_attempts

    @model_validator(mode="after")
    def viable_limits(self) -> Self:
        if self.max_entries < self.minimum_entries:
            raise ValueError("Entry budget cannot hold the declared normal batch")
        if self.max_bytes < self.minimum_entries * (self.max_entry_bytes + 1):
            raise ValueError("Byte budget cannot hold bounded entries and closures")
        return self

    def preflight(self, envelope_bytes: int) -> None:
        """Include the actual frozen binding/capacity JSON wrapper before create."""
        if type(envelope_bytes) is not int or envelope_bytes < 0:
            raise ValueError("Envelope size must be a nonnegative integer")
        if (
            envelope_bytes + self.minimum_entries * (self.max_entry_bytes + 1)
            > self.max_bytes
        ):
            raise JournalCapacityExceeded(
                "Frozen envelope leaves insufficient batch space"
            )

    def check(
        self,
        *,
        entries: int,
        encoded_bytes: int,
        pending_closures: int,
        attempts: int,
    ) -> None:
        """Proposed commit must leave room for every remaining closure event."""
        for value in (entries, encoded_bytes, pending_closures, attempts):
            if type(value) is not int or value < 0:
                raise ValueError("Capacity usage must contain nonnegative integers")
        if attempts > self.max_attempts:
            raise JournalCapacityExceeded("Declared attempt budget exhausted")
        if entries + pending_closures > self.max_entries:
            raise JournalCapacityExceeded("Event budget must retain closure reserve")
        if (
            encoded_bytes + pending_closures * (self.max_entry_bytes + 1)
            > self.max_bytes
        ):
            raise JournalCapacityExceeded("Byte budget must retain closure reserve")
