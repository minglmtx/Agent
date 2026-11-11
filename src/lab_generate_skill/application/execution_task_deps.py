"""Actor-only dependencies implement the same common task execution interface."""

from dataclasses import dataclass, field
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.evaluator import Evaluator
from lab_generate_skill.ports.state_records import StateRecords
from lab_generate_skill.ports.lifecycle import Clock, OperationControls
from lab_generate_skill.ports.actor_admission import CandidateInputs
from lab_generate_skill.ports.execution_task import (
    ExecutionTaskSources,
    ExecutionTaskAuthority,
)
from lab_generate_skill.ports.task_admission import TaskLifecycleAdmission
from lab_generate_skill.ports.task_execution import (
    TaskPreparation,
    TaskInitialization,
    TaskCapture,
    TaskFinalization,
    TaskActorBinding,
)
from .execution_task_admission import ExecutionTaskAdmission


@dataclass(frozen=True)
class ExecutionTaskExecutionDeps:
    source_reader: ExecutionTaskSources
    inputs: CandidateInputs
    claims: SourceClaims
    runs: RunJournal
    preparation: TaskPreparation
    initialization: TaskInitialization
    actors: TaskActorBinding
    capture: TaskCapture
    evaluator: Evaluator
    finalization: TaskFinalization
    states: StateRecords
    authority: ExecutionTaskAuthority
    evidence: EvidenceStore
    controls: OperationControls
    clock: Clock
    source: TaskLifecycleAdmission = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", ExecutionTaskAdmission(self))
