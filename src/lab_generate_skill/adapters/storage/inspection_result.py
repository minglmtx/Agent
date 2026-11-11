"""Original storage observations, with partial facts retained on failure.

These are observations of one pinned directory, never worker termination,
cleanup permission or proof that a session is reusable. No payload is retained.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from lab_generate_skill.domain.evidence_io import EvidenceCommand


@dataclass(frozen=True)
class StorageFileIdentity:
    device: int
    inode: int
    mode: int
    size: int


@dataclass(frozen=True)
class StorageObservation:
    command: EvidenceCommand
    observed_at: datetime
    root: StorageFileIdentity | None
    blobs: StorageFileIdentity | None
    object_state: Literal["present", "absent", "unknown"]
    temporary_name: str | None
    temporary_state: Literal["absent", "present", "unsafe", "unknown", "not_applicable"]
    temporary: StorageFileIdentity | None


class StorageInspectionFailure(Exception):
    """Original exception/group is the cause; partial observations are not clean."""

    def __init__(self, phase: str, observation: StorageObservation) -> None:
        super().__init__("Original evidence storage inspection failed: " + phase)
        self.phase = phase
        self.observation = observation
