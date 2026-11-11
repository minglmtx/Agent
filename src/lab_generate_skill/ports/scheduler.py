"""Read-only scheduler probe. No submit, cancel, requeue or takeover methods."""

from typing import Protocol

from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.scheduler import (
    SlurmExecutionIdentity,
    SlurmJobObservation,
)


class SlurmJobProbe(Protocol):
    """Observe an already pinned execution with bounded, non-retrying queries.

    Missing/duplicate/mismatched accounting and failed/truncated queue queries
    raise with evidence; an empty successful queue is only an absence fact.
    Every call makes a fresh observation. No result proves descendant exit.
    """

    def observe(
        self, execution: SlurmExecutionIdentity, op: OperationContext
    ) -> SlurmJobObservation: ...
