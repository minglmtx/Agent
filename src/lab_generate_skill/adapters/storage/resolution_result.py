"""Inspection/recording outcome; a candidate is never a commit acknowledgement."""

from dataclasses import dataclass
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionResolution
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from .inspection_result import StorageObservation


@dataclass(frozen=True)
class RegisteredStorageResolution:
    resolution: EvidenceSessionResolution
    observation: StorageObservation | None
    snapshot: EvidenceSessionSnapshot | None


class StorageResolutionFailure(Exception):
    def __init__(self, result: RegisteredStorageResolution) -> None:
        super().__init__("Original evidence storage resolution failed")
        self.result = result


def retained_storage_resolution(
    error: BaseException,
) -> RegisteredStorageResolution | None:
    from lab_generate_skill.adapters.processes.exception_facts import exception_chain

    for current in exception_chain(error):
        if isinstance(current, StorageResolutionFailure):
            return current.result
        observed = getattr(current, "storage_resolution", None)
        if isinstance(observed, RegisteredStorageResolution):
            return observed
    return None
