"""Actual initial/preparation/DOM producers, passive capture and original close."""

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.bootstrap.shopping_category_initial_capture import (
    CapturedCategoryNavigationInitialChecks,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.sites.shopping.navigation_page_capture import (
    ShoppingCategoryPageCollector,
)
from shopping_category_browser_fixtures import Page
from shopping_prepared_family_fixtures import prepared_family_case
from preparation_record_fixtures import put
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "observation",
        "collector",
        "configuration",
        "request",
        "old",
        "http",
        "unknown",
        "login",
        "error",
        "url",
        "loading",
        "noncanonical",
        "missing",
    ],
)
def test_original_passive_category_capture_binds_full_initial_inputs_and_document_health(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    saved: dict[str, Any] = {}

    def ready(c: dict[str, Any]) -> None:
        saved.update(c)
        store, browser = c["store"], c["browser_case"]
        initial = InitialObservationReader(store, c["preparations"]).load(
            c["initial_selection"], c["prepare"].operation, guard()
        )
        request = BrowserCaptureRequest(
            scope=initial.prepared.scope,
            operation=browser.op.model_copy(
                update={"operation_id": "category-original-first-page"}
            ),
            observation_sha256=c["session"].observation_ref.sha256,
            collector_id="shopping-category-navigation-page",
            collector_version="1",
        )
        if fault == "observation":
            request = request.model_copy(update={"observation_sha256": "f" * 64})
        elif fault == "collector":
            request = request.model_copy(update={"collector_id": "foreign"})
        intent = BrowserCaptureIntent(
            request=request,
            configuration_sha256=hashlib.sha256(
                browser.spec.configuration.model_dump_json().encode()
            ).hexdigest(),
        )
        if fault == "configuration":
            intent = intent.model_copy(update={"configuration_sha256": "f" * 64})
        page = Page(c["public"])
        page.url = c["public"].start_url
        if fault == "http":
            page.health["http_status"] = 500
        elif fault == "unknown":
            page.health.update(http_status=None, status_source="unavailable")
        elif fault in ("login", "error"):
            page.health["login_page" if fault == "login" else "error_page"] = True
        elif fault == "url":
            page.url += "foreign"
            page.health["url"] = page.url
        elif fault == "loading":
            page.ready = "loading"
        raw = ShoppingCategoryPageCollector().collect(
            page, "shopping-category-navigation-page", "1", guard()
        )
        # The collector recomputes error_page from its original URL/status/title.
        if fault == "error":
            page.health.update(title="503 Service Unavailable", http_status=503)
            raw = ShoppingCategoryPageCollector().collect(
                page, "shopping-category-navigation-page", "1", guard()
            )
        result = BrowserCaptureResult(
            request_sha256=request.digest,
            captured_at=datetime.now(timezone.utc),
            private_result=raw,
        )
        if fault == "request":
            result = result.model_copy(update={"request_sha256": "f" * 64})
        elif fault == "old":
            result = result.model_copy(
                update={
                    "captured_at": initial.observation.record.captured_at
                    - timedelta(seconds=1)
                }
            )
        elif fault == "noncanonical":
            result = result.model_copy(update={"private_result": raw + " "})
        intent_ref, result_ref = put(store, intent), put(store, result)
        selected = CapturedCategoryNavigationInitialChecks(
            store, intent_ref, result_ref
        )
        if fault == "missing":
            original = store.read

            def read(reference: Any, control: Any = None) -> bytes:
                if reference == result_ref:
                    raise EvidenceIntegrityError(
                        "Unit original initial capture missing"
                    )
                raw: bytes = original(reference, control=control)
                assert type(raw) is bytes
                return raw

            monkeypatch.setattr(store, "read", read)
        if fault == "none":
            checks = selected.check(initial, guard())
            assert checks == c["baseline_inputs"].initial.checks
        else:
            with pytest.raises((EvidenceIntegrityError, OwnershipConflict)):
                selected.check(initial, guard())
        assert initial.observation.record.sequence == 0
        assert browser.channels[0].engine.calls == ["start"]

    prepared_family_case(
        tmp_path,
        node_path,
        monkeypatch,
        "none",
        category=(originals[0][0], originals[0][2]),
        on_ready=ready,
    )
    browser = saved["browser_case"]
    assert browser.journal.read(browser.spec.token, browser.op).state == "closed"
    assert browser.channels[0].engine.calls == ["start", "close"]
