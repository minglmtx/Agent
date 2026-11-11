"""Pure current-pointer history: CAS, exact replay and immutable release labels.

An earlier switch replay returns today's snapshot; it never reactivates the old
release. Capacity exhaustion refuses new switches and preserves readable facts.
"""

from typing import Literal, Self
from pydantic import model_validator
from .errors import OwnershipConflict, RevisionConflict, JournalCapacityExceeded
from .lifecycle import OperationContext
from .release_activation import (
    ReleaseDeployment,
    ReleaseActivation,
    ReleaseSwitch,
    check_publication_operation,
)
from .validation import Contract

MAX_CURRENT_BYTES = 8 * 1024 * 1024


class ReleaseCurrentSnapshot(Contract):
    schema_version: Literal["release-current/1"] = "release-current/1"
    deployment: ReleaseDeployment
    initialized_by: OperationContext
    switches: tuple[ReleaseSwitch, ...] = ()

    @property
    def revision(self) -> int:
        return len(self.switches)

    @property
    def active(self) -> ReleaseActivation | None:
        return self.switches[-1].activation if self.switches else None

    @model_validator(mode="after")
    def valid_history(self) -> Self:
        check_publication_operation(self.initialized_by)
        if len(self.switches) > self.deployment.max_switches:
            raise JournalCapacityExceeded("Release switch history is full")
        operations = {self.initialized_by.operation_id}
        releases: dict[str, tuple[object, object]] = {}
        for revision, switch in enumerate(self.switches):
            if switch.expected_revision != revision:
                raise ValueError("Release switch history skips a revision")
            if switch.operation.operation_id in operations:
                raise OwnershipConflict("Release publication operation is reused")
            operations.add(switch.operation.operation_id)
            active = switch.activation
            identity = (active.manifest_ref, active.registry_ref)
            if (
                active.release_id in releases
                and releases[active.release_id] != identity
            ):
                raise OwnershipConflict(
                    "Release label was rebound to different evidence"
                )
            releases[active.release_id] = identity
        if len(self.model_dump_json().encode()) > MAX_CURRENT_BYTES:
            raise JournalCapacityExceeded("Release current exceeds its byte limit")
        return self


def switch_release(
    prior: ReleaseCurrentSnapshot, change: ReleaseSwitch
) -> ReleaseCurrentSnapshot:
    prior = ReleaseCurrentSnapshot.model_validate(prior)
    change = ReleaseSwitch.model_validate(change)
    if change.operation.operation_id == prior.initialized_by.operation_id:
        raise OwnershipConflict("Initialization operation cannot activate a release")
    for old in prior.switches:
        if old.operation.operation_id == change.operation.operation_id:
            if old != change:
                raise OwnershipConflict("Original publication operation changed")
            return prior
    if change.expected_revision != prior.revision:
        raise RevisionConflict("Release current revision changed")
    # Refuse valid commands at capacity with the public domain exception.
    # Pydantic wraps ValueError subclasses raised inside model validators;
    # deserializing an invalid snapshot and rejecting a new command differ.
    if prior.revision >= prior.deployment.max_switches:
        raise JournalCapacityExceeded("Release switch history is full")
    candidate = prior.model_copy(update={"switches": prior.switches + (change,)})
    if len(candidate.model_dump_json().encode()) > MAX_CURRENT_BYTES:
        raise JournalCapacityExceeded("Release current exceeds its byte limit")
    return ReleaseCurrentSnapshot.model_validate(candidate)
