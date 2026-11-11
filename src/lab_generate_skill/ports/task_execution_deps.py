"""Common read-only dependency interface for the single task lifecycle."""

from typing import Protocol
from .task_admission import TaskLifecycleAdmission
from .run_journal import RunJournal
from .evidence import EvidenceStore
from .evaluator import Evaluator
from .state_records import StateRecords
from .lifecycle import Clock, OperationControls
from .task_execution import (
    TaskPreparation,
    TaskInitialization,
    TaskActorBinding,
    TaskCapture,
    TaskFinalization,
    TaskClosureAuthority,
)


class TaskExecutionDeps(Protocol):
    @property
    def source(self) -> TaskLifecycleAdmission: ...

    @property
    def runs(self) -> RunJournal: ...

    @property
    def preparation(self) -> TaskPreparation: ...

    @property
    def initialization(self) -> TaskInitialization: ...

    @property
    def actors(self) -> TaskActorBinding: ...

    @property
    def capture(self) -> TaskCapture: ...

    @property
    def evaluator(self) -> Evaluator: ...

    @property
    def finalization(self) -> TaskFinalization: ...

    @property
    def states(self) -> StateRecords: ...

    @property
    def authority(self) -> TaskClosureAuthority: ...

    @property
    def evidence(self) -> EvidenceStore: ...

    @property
    def controls(self) -> OperationControls: ...

    @property
    def clock(self) -> Clock: ...
