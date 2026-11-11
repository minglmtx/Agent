"""Original claimed Actor provider with an independent observation lifetime.

The existing registered_actor owns acquisition, process close and journaling.
The outer authority scope only releases its kernel observation handles when a
partial failure prevents the normal verification callback.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.models.actor_resource import registered_actor
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.models.claimed_resource_authority import (
    ClaimedActorResourceAuthority,
)
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls, Clock


@contextmanager
def claimed_actor_resource(
    owner: ClaimedRunResourceOwner,
    spec: ActorResourceSpec,
    acquisition: OperationContext,
    *,
    journal: ResourceJournal,
    controls: OperationControls,
    clock: Clock,
    workspace_root: Path,
    allocation_verifier: SlurmAllocationVerifier,
    cleanup_seconds: int | None = None,
) -> Iterator[SupervisedActorEngine]:
    with ClaimedActorResourceAuthority(owner, spec, acquisition) as authority:
        with registered_actor(
            spec,
            acquisition,
            journal=journal,
            evidence=owner.evidence,
            controls=controls,
            clock=clock,
            authority=authority,
            workspace_root=workspace_root,
            allocation_verifier=allocation_verifier,
            cleanup_seconds=(
                owner.task_plan.cleanup_seconds
                if cleanup_seconds is None
                else cleanup_seconds
            ),
        ) as engine:
            yield engine
