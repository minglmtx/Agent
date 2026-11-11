"""Original category first-document facts; no navigation or permission."""

import hashlib
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .navigation_page import CategoryNavigationPage


def require_category_initial_capture(
    initial: InitialObservationInputs,
    intent: BrowserCaptureIntent,
    result: BrowserCaptureResult,
) -> CategoryNavigationPage:
    initial = InitialObservationInputs.model_validate(initial)
    intent = BrowserCaptureIntent.model_validate(intent)
    result = BrowserCaptureResult.model_validate(result)
    browser = initial.browser
    request = intent.request
    request.check_readout(browser.configuration.spec, initial.returned)
    browser.check_operation(request.operation, "execute")
    page = CategoryNavigationPage.model_validate_json(result.private_result)
    health = page.health
    if (
        initial.observation.record.sequence != 0
        or (request.collector_id, request.collector_version)
        != ("shopping-category-navigation-page", "1")
        or intent.configuration_sha256
        != hashlib.sha256(browser.configuration.model_dump_json().encode()).hexdigest()
        or result.request_sha256 != request.digest
        or result.captured_at < initial.observation.record.captured_at
        or request.operation.operation_id
        in (
            initial.returned.operation.operation_id,
            initial.acquired.operation.operation_id,
        )
        or page.model_dump_json() != result.private_result
        or page.document_ready != "complete"
        or page.navigation_policy_block is not None
        or health.url != initial.prepared.public_task.start_url
        or health.status_source != "navigation_timing"
        or health.http_status is None
        or not 200 <= health.http_status < 400
        or health.login_page
        or health.error_page
    ):
        raise EvidenceIntegrityError(
            "Category initial capture lost original healthy first document"
        )
    return page
