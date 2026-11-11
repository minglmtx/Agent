"""Known current initialization facts retained independently of returned success."""

from dataclasses import dataclass, field
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.initial_equivalence import EquivalenceReceipt
from lab_generate_skill.domain.task_execution import InitializedTask


@dataclass
class TaskInitializationState:
    phase: str = "new"
    references: list[EvidenceRef] = field(default_factory=list)
    candidates: list[EvidenceRef] = field(default_factory=list)
    selection: InitialObservationSelection | None = None
    baseline_inputs: BaselineInputs | None = None
    baseline: BaselineReceipt | None = None
    baseline_ref: EvidenceRef | None = None
    equivalence: EquivalenceReceipt | None = None
    equivalence_ref: EvidenceRef | None = None
    result: InitializedTask | None = None
