"""Original capture predicates and refusals; all resource/model facts are unit.

These tests cannot qualify an actual Admin source, physical owner or execution.
The actual protected fixed-worker path is separately exercised with retained Map.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.admin_navigation_initial_capture import (
    CapturedAdminNavigationInitialChecks,
)
from lab_generate_skill.bootstrap.admin_navigation_source_qualification import (
    qualify_admin_navigation_source,
)
from lab_generate_skill.bootstrap.admin_navigation_source_publication import (
    publish_admin_navigation_source,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.shopping_admin.navigation_evidence_schema import (
    AdminNavigationPage,
)
from admin_navigation_terminal_fixtures import terminal_case
from preparation_record_fixtures import put
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault", ["none", "login", "error", "url", "scope", "configuration"]
)
def test_source_and_terminal_share_exact_authenticated_initial_capture_predicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any, fault: str
) -> None:
    with terminal_case(tmp_path, monkeypatch, contracts, current=True) as c:
        selected = c.selection
        intent = BrowserCaptureIntent.model_validate_json(
            c.store.read(selected.initial_capture_intent_ref)
        )
        result = BrowserCaptureResult.model_validate_json(
            c.store.read(selected.initial_capture_result_ref)
        )
        if fault in ("login", "error", "url"):
            page = AdminNavigationPage.model_validate_json(result.private_result)
            page = page.model_copy(
                update=(
                    {"login": True}
                    if fault == "login"
                    else (
                        {"page_error": True}
                        if fault == "error"
                        else {"url": page.url + "/foreign"}
                    )
                )
            )
            result = result.model_copy(
                update={"private_result": page.model_dump_json()}
            )
        if fault == "scope":
            intent = intent.model_copy(
                update={
                    "request": intent.request.model_copy(
                        update={
                            "scope": intent.request.scope.model_copy(
                                update={"context_id": "foreign"}
                            )
                        }
                    )
                }
            )
        if fault == "configuration":
            intent = intent.model_copy(update={"configuration_sha256": "0" * 64})
        checker = CapturedAdminNavigationInitialChecks(
            c.store, put(c.store, intent), put(c.store, result)
        )
        if fault == "none":
            assert checker.check(c.initial, guard(30)).status == "pass"
        else:
            with pytest.raises(EvidenceIntegrityError):
                checker.check(c.initial, guard(30))


@pytest.mark.parametrize("value", [None, "", 0, True, {}, []])
def test_source_qualification_and_publication_reject_untyped_owners_before_effects(
    value: Any,
) -> None:
    with pytest.raises(TypeError):
        qualify_admin_navigation_source(
            value,
            value,
            value,
            value,
            value,
            value,
            value,
            journal=value,
            controls=value,
            clock=value,
            prefix="source",
            metadata_seconds=1,
            source_reads=value,
        )
    with pytest.raises(TypeError):
        publish_admin_navigation_source(value, value, value, value, source_reads=value)
