"""Original Group unique0 plus the captured native authenticated document."""

import hashlib
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.state_scope import private_state_ref
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..evidence_schema import GitlabPageHealth
from ..private_state_reads import GitlabPrivateReads
from .group_initial_observation import GroupInitialObservationChecks


class CapturedGroupInitialChecks:
    def __init__(
        self, evidence: EvidenceReader, intent: EvidenceRef, result: EvidenceRef
    ) -> None:
        private_state_ref(intent, "browser-capture-intent/1")
        private_state_ref(result, "browser-capture-result/1")
        self.intent, self.result = intent, result
        self.reads = GitlabPrivateReads(evidence)

    def check(
        self, inputs: InitialObservationInputs, control: OperationControl
    ) -> StateChecks:
        checks = GroupInitialObservationChecks().check(inputs, control)
        cfg = inputs.browser.configuration
        selected = cfg.initialization
        if not isinstance(selected, GitlabGroupInitialization):
            raise EvidenceIntegrityError("Original Group initialized browser required")
        intent = self.reads.read(
            self.intent, "browser-capture-intent/1", BrowserCaptureIntent, control
        )
        result = self.reads.read(
            self.result, "browser-capture-result/1", BrowserCaptureResult, control
        )
        request = intent.request
        page = GitlabPageHealth.model_validate_json(result.private_result)
        inputs.browser.check_operation(request.operation, "execute")
        if (
            request.scope != inputs.prepared.scope
            or request.observation_sha256
            != inputs.acquired.details.started.initial_observation_ref.sha256
            or (request.collector_id, request.collector_version)
            != ("gitlab-page-health", "1")
            or intent.configuration_sha256
            != hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()
            or result.request_sha256 != request.digest
            or result.captured_at < inputs.observation.record.captured_at
            or page.model_dump_json() != result.private_result
            or page.url != inputs.prepared.public_task.start_url
            or page.login_page
            or page.error_page
            or page.account_id != selected.native_account_id
            or page.http_status is None
            or not 200 <= page.http_status < 300
            or page.status_source != "navigation_timing"
        ):
            raise EvidenceIntegrityError(
                "Group source lost original authenticated healthy initial capture"
            )
        control.checkpoint()
        return checks
