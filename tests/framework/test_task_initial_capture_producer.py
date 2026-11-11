"""Production initializer/measurement/capture join with explicit unit live rights."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.browsergym.task_capture_authority import (
    OriginalTaskBrowserCaptureAuthority,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.adapters.sites.task_resource_owner import (
    OriginalTaskResourceOwner,
)
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from task_initialization_port_fixtures import initialization_case
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "collector", ["map-navigation-initial", "admin-navigation-page"]
)
@pytest.mark.parametrize(
    "fault", ["none", "collector", "version", "producer", "phase", "revoked"]
)
def test_actual_measurement_intent_uses_bound_producer_and_closes_original_browser(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, collector: str, fault: str
) -> None:
    with initialization_case(node_path, monkeypatch) as c:
        initial, browser = c.initialization, c.browser
        measurement = initial.measurements
        assert isinstance(measurement, CapturedTaskInitialMeasurements)
        measurement.collector_id = collector
        store = c.preparation.original.resource.evidence

        class UnitResources(OriginalTaskResourceOwner):
            def __init__(self) -> None:
                self.owner = cast(
                    ClaimedRunResourceOwner, SimpleNamespace(reads=StateReads(store))
                )

            def require_browser(self, operation: Any, control: Any) -> Any:
                control.checkpoint()
                if fault == "revoked":
                    raise PermissionError("Unit current browser permission revoked")
                return browser

        authority = OriginalTaskBrowserCaptureAuthority(
            UnitResources(),
            lambda: initial,
            lambda: pytest.fail("Initial capture must not request terminal producer"),
            lambda: pytest.fail("Initial capture must not request Actor trace"),
        )
        measurement.authority = authority
        reached: list[str] = []
        original_verify = authority.verify_capture

        def verify(configuration: Any, request: Any, ref: Any, control: Any) -> None:
            if fault == "collector":
                request = request.model_copy(update={"collector_id": "foreign"})
            elif fault == "version":
                request = request.model_copy(update={"collector_version": "other"})
            elif fault == "producer":
                monkeypatch.setattr(measurement, "authority", object())
            elif fault == "phase":
                initial.state.phase = "complete"
            original_verify(configuration, request, ref, control)
            reached.append(request.collector_id)
            if collector == "admin-navigation-page":
                # The Map website double has no Admin codec. Stop only after the
                # actual producer/intent/authority seam; do not fake native data.
                raise RuntimeError("Accepted Admin collector reached wire boundary")

        monkeypatch.setattr(authority, "verify_capture", verify)
        if fault == "none" and collector == "map-navigation-initial":
            result = c.start()
            assert (
                result.actor.initial_observation_ref == browser.session.observation_ref
            )
            assert reached == [collector]
        else:
            with pytest.raises(TaskInitializationUnconfirmed) as caught:
                c.start()
            if fault == "none":
                assert reached == [collector]
                assert isinstance(caught.value.primary, RuntimeError)
                assert (
                    str(caught.value.primary)
                    == "Accepted Admin collector reached wire boundary"
                )
            else:
                assert reached == []
                assert isinstance(
                    caught.value.primary, (OwnershipConflict, PermissionError)
                )
            assert measurement.attempted
            assert measurement.capture is not None
            assert measurement.capture.intent_ref is not None
            with pytest.raises(DispatchAlreadyCommitted):
                c.start()
    assert browser.phase == "closed"
