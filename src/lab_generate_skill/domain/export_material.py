"""Private typed source material; never serialized into Generator messages."""

from dataclasses import dataclass
from .construction_state import ConstructionProgress
from .construction_inputs import GenerationInput
from .review import ReviewReceipt
from .generator_model import GeneratorModelRequest
from .export import TrainingTargetQualification
from .data_scope import SplitMember
from .skill import CompactSkill
from .evidence import EvidenceRef
from .run_plan import RunPlan
from .task_execution import TaskExecutionPlan


@dataclass(frozen=True)
class ExportMaterial:
    recorded: ReviewReceipt
    current: ReviewReceipt
    progress: ConstructionProgress
    run_plan: RunPlan
    qualification: TrainingTargetQualification
    member: SplitMember
    generation_input_ref: EvidenceRef
    generation: GenerationInput
    prompt: GeneratorModelRequest
    selected_skill: CompactSkill | None
    selected_task: TaskExecutionPlan | None
