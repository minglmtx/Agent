"""Read exact initial capture references, retaining original navigation checks."""

from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.evidence_schema import PageCaptureEvidence
from lab_generate_skill.sites.shopping_admin.tasks.navigation_initial_observation import (
    NavigationInitialObservationChecks,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_initial_capture import (
    require_navigation_initial_capture,
)


class CapturedAdminNavigationInitialChecks:
    def __init__(
        self, evidence: EvidenceReader, intent: EvidenceRef, result: EvidenceRef
    ) -> None:
        self.selected = PageCaptureEvidence(intent_ref=intent, result_ref=result)
        self.reads = StateReads(evidence)

    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks:
        checks = NavigationInitialObservationChecks().check(inputs, control)
        intent = self.reads.parse(
            self.selected.intent_ref,
            "browser-capture-intent/1",
            BrowserCaptureIntent,
            control,
        )
        result = self.reads.parse(
            self.selected.result_ref,
            "browser-capture-result/1",
            BrowserCaptureResult,
            control,
        )
        require_navigation_initial_capture(inputs, intent, result)
        control.checkpoint()
        return checks
