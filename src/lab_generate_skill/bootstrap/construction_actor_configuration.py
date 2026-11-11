"""Bind new construction plans to the existing actual Actor assembly."""

from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.plans.construction_actor_capabilities import (
    selected_actor_capabilities,
)
from lab_generate_skill.domain.construction import ConstructionPlan
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_execution import TaskActorBinding
from .task_actor import CurrentTaskActorBinding


def verify_selected_construction_factory(
    plan: ConstructionPlan,
    task: TaskExecutionPlan,
    actors: TaskActorBinding,
    evidence: EvidenceReader,
    control: OperationControl,
) -> None:
    if plan.actor_context_configuration_ref is None:
        return
    if type(actors) is not CurrentTaskActorBinding or actors.plan != task:
        raise OwnershipConflict(
            "Selected construction Actor requires the actual original current-task assembly, not a capability flag"
        )
    selected_actor_capabilities(plan, StateReads(evidence), control)
