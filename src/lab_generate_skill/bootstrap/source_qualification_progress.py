"""Owner-local returned source facts; existing journals/CAS own durable history."""

from dataclasses import dataclass, field
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.sites.source_qualification_native import (
    PendingQualificationNative,
)
from lab_generate_skill.adapters.sites.source_qualification_records import (
    QualificationPreparationFacts,
)
from lab_generate_skill.adapters.sites.source_qualification_resume import (
    PendingQualificationResume,
)
from lab_generate_skill.adapters.sites.source_qualification_state import (
    QualificationStateSelections,
)
from lab_generate_skill.domain.baseline import BaselineInputs, BaselineReceipt
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.reset import ResetPlan, ResetInputs, ResetReceipt
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult


@dataclass
class SourceQualificationProgress:
    phase: str = "declared"
    input_reuse: dict[str, int] = field(default_factory=dict)
    references: list[EvidenceRef] = field(default_factory=list)
    pending_native: PendingQualificationNative | None = None
    pending_resume: PendingQualificationResume | None = None
    selections: QualificationStateSelections | None = None
    preparation: QualificationPreparationFacts | None = None
    reset_plan: ResetPlan | None = None
    reset_plan_ref: EvidenceRef | None = None
    environment: EnvironmentBaseline | None = None
    environment_ref: EvidenceRef | None = None
    snapshot_request: SiteTaskRequest | None = None
    snapshot_ref: EvidenceRef | None = None
    prepare_request: SiteTaskRequest | None = None
    prepare_result: SiteTaskResult | None = None
    publication: PreparedPublication | None = None
    browser: RetainedBrowserResource | None = None
    browser_closure_ref: EvidenceRef | None = None
    capture_request: BrowserCaptureRequest | None = None
    capture_intent_ref: EvidenceRef | None = None
    capture_result_ref: EvidenceRef | None = None
    initial: InitialObservationSelection | None = None
    baseline_inputs: BaselineInputs | None = None
    baseline: BaselineReceipt | None = None
    restore_attempted: bool = False
    reset_inputs: ResetInputs | None = None
    reset: ResetReceipt | None = None
