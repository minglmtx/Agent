"""Concrete original construction dependencies for the one task lifecycle."""

from lab_generate_skill.ports.construction_task_execution import TaskExecutionAuthority

from dataclasses import dataclass, field
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.evaluator import Evaluator
from lab_generate_skill.ports.state_records import StateRecords
from lab_generate_skill.ports.lifecycle import Clock, OperationControls
from lab_generate_skill.ports.task_execution import (
    TaskPreparation,
    TaskInitialization,
    TaskActorBinding,
    TaskCapture,
    TaskFinalization,
)
from lab_generate_skill.ports.task_admission import TaskLifecycleAdmission
from .admit_candidate import CandidateAdmissionDeps
from .construction_task_admission import ConstructionTaskAdmission


@dataclass(frozen=True)
class ConstructionTaskExecutionDeps:
    construction: ConstructionJournal
    runs: RunJournal
    admission: CandidateAdmissionDeps
    preparation: TaskPreparation
    initialization: TaskInitialization
    actors: TaskActorBinding
    capture: TaskCapture
    evaluator: Evaluator
    finalization: TaskFinalization
    states: StateRecords
    authority: TaskExecutionAuthority
    evidence: EvidenceStore
    controls: OperationControls
    clock: Clock

    source: TaskLifecycleAdmission = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", ConstructionTaskAdmission(self))
