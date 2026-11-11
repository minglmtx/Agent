"""Original authenticated initial capture predicate, shared by source and task."""

import hashlib
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from ..navigation_evidence_schema import AdminNavigationPage


def require_navigation_initial_capture(
    initial: InitialObservationInputs,
    intent: BrowserCaptureIntent,
    result: BrowserCaptureResult,
) -> AdminNavigationPage:
    config, scope = initial.browser.configuration, initial.prepared.scope
    initial_ref = initial.acquired.details.started.initial_observation_ref
    page = AdminNavigationPage.model_validate_json(result.private_result)
    request = intent.request
    if (
        request.scope != scope
        or request.observation_sha256 != initial_ref.sha256
        or (request.collector_id, request.collector_version)
        != ("admin-navigation-page", "1")
        or intent.configuration_sha256
        != hashlib.sha256(config.model_dump_json().encode()).hexdigest()
        or result.request_sha256 != request.digest
        or result.captured_at < initial.observation.record.captured_at
        or page.model_dump_json() != result.private_result
        or page.url != initial.prepared.public_task.start_url
        or page.login
        or page.page_error
    ):
        raise EvidenceIntegrityError(
            "Navigation terminal lost original authenticated initial capture"
        )
    return page
