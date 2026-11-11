"""Actual category producer/capture permission join; upstream live rights unit-only."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.adapters.browsergym.task_capture_authority import (
    OriginalTaskBrowserCaptureAuthority,
)
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.bootstrap.shopping_category_task_initialization import (
    shopping_category_task_initialization,
)
import shopping_category_initialization_port_fixtures as fixtures
from site_instance_fixtures import node_path as node_path
from test_shopping_category_navigation_input import originals as originals


@pytest.mark.parametrize(
    "fault", ["none", "collector", "version", "producer", "phase", "revoked"]
)
def test_category_actual_initial_collector_authority_and_original_close(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    original = shopping_category_task_initialization
    instances: list[RecordedTaskInitialization] = []
    reached: list[str] = []

    def factory(*args: Any, **kwargs: Any) -> RecordedTaskInitialization:
        initial = original(*args, **kwargs)
        instances.append(initial)
        measurement = initial.measurements
        assert isinstance(measurement, CapturedTaskInitialMeasurements)
        assert measurement.collector_id == "shopping-category-navigation-page"
        browser = initial.browser

        class UnitResources(OriginalTaskResourceOwner):
            def __init__(self) -> None:
                self.owner = cast(
                    ClaimedRunResourceOwner,
                    SimpleNamespace(reads=StateReads(initial.evidence)),
                )

            def require_browser(self, operation: Any, control: Any) -> Any:
                control.checkpoint()
                if fault == "revoked":
                    raise PermissionError("Current unit category browser revoked")
                return browser

        authority = OriginalTaskBrowserCaptureAuthority(
            UnitResources(),
            lambda: initial,
            lambda: pytest.fail("Initial capture cannot request terminal capture"),
            lambda: pytest.fail("Initial capture cannot request Actor trace"),
        )
        measurement.authority = authority
        verify_original = authority.verify_capture

        def verify(configuration: Any, request: Any, ref: Any, control: Any) -> None:
            if fault == "collector":
                request = request.model_copy(update={"collector_id": "foreign"})
            elif fault == "version":
                request = request.model_copy(update={"collector_version": "other"})
            elif fault == "producer":
                monkeypatch.setattr(measurement, "authority", object())
            elif fault == "phase":
                initial.state.phase = "complete"
            verify_original(configuration, request, ref, control)
            reached.append(request.collector_id)

        monkeypatch.setattr(authority, "verify_capture", verify)
        return initial

    monkeypatch.setattr(fixtures, "shopping_category_task_initialization", factory)
    facts = fixtures.initialization_case(
        tmp_path,
        node_path,
        monkeypatch,
        originals[0],
        "none" if fault == "none" else "capture-denied",
    )
    assert facts["closed"] and facts["source_attempt"] != facts["candidate_attempt"]
    assert instances and all(i._current_initial is None for i in instances)
    if fault == "none":
        assert reached == ["shopping-category-navigation-page"]
        assert facts["capture_calls"] == 1 and facts["body_admission_count"] == 5
        assert facts["result"].actor.task.identity == originals[0][2].identity
    else:
        assert reached == []
        assert facts["primary"] == (
            "PermissionError" if fault == "revoked" else "OwnershipConflict"
        )
