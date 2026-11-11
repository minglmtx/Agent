"""Known partial cleanup facts, subordinate to original run/resource ledgers."""

from dataclasses import dataclass, field
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task_execution import ClosedTaskResources
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.state_qualification import ResetSelection
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt
from lab_generate_skill.domain.reset_publication import PublishedReset


@dataclass
class TaskFinalizationState:
    phase: str = "new"
    close_attempted: bool = False
    restore_attempted: bool = False
    references: list[EvidenceRef] = field(default_factory=list)
    closed: ClosedTaskResources | None = None
    restore_request: SiteTaskRequest | None = None
    restore_request_ref: EvidenceRef | None = None
    restore_result: SiteTaskResult | None = None
    restore_result_ref: EvidenceRef | None = None
    resume_request: SiteResumeRequest | None = None
    resume_request_ref: EvidenceRef | None = None
    resume_intent_ref: EvidenceRef | None = None
    resume_result_ref: EvidenceRef | None = None
    reset_selection: ResetSelection | None = None
    reset_selection_ref: EvidenceRef | None = None
    reset_inputs: ResetInputs | None = None
    reset: ResetReceipt | None = None
    reset_ref: EvidenceRef | None = None
    reset_publication: PublishedReset | None = None
