"""Retain original partial collection facts without another request ledger."""

from dataclasses import dataclass, field
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task_capture import TaskCaptureInputs
from lab_generate_skill.domain.task_execution import TaskCaptureResult


@dataclass
class TaskCaptureState:
    phase: str = "new"
    inputs: TaskCaptureInputs | None = None
    references: list[EvidenceRef] = field(default_factory=list)
    candidates: list[EvidenceRef] = field(default_factory=list)
    terminal_ref: EvidenceRef | None = None
    closure_ref: EvidenceRef | None = None
    selection_ref: EvidenceRef | None = None
    result: TaskCaptureResult | None = None
