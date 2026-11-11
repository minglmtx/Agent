"""Category passive initial capture, original owner and cleanup; no source grant.

Only measurement is consumed here. Source/prepared-result/Actor declarations are
explicit contract premises, not real producers or full initialization acceptance.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.initial_measurements import (
    CapturedTaskInitialMeasurements,
)
from lab_generate_skill.bootstrap.shopping_category_records import (
    category_initial_observations,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.baseline import InitialStateChecks
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.navigation_page_capture import (
    ShoppingCategoryPageCollector,
)
from initial_observation_fixtures import Authority as InitialAuthority
from shopping_category_browser_fixtures import Page
from shopping_prepared_family_fixtures import prepared_family_case
from test_browser_capture import Authority as CaptureAuthority
from test_task_initialization_contracts import declaration
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault", ["none", "capture-denied", "result-write", "initial-write", "cancel"]
)
def test_category_original_initial_capture_keeps_first_return_and_closes_after_failure(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    def ready(c: dict[str, Any]) -> None:
        b, owner, session, store = (
            c["browser_case"],
            c["browser_owner"],
            c["session"],
            c["store"],
        )
        assert owner.session is session and owner.phase == "open"
        template = declaration()
        start = b.op
        stages = {
            name: start.model_copy(
                update={"operation_id": "category-" + name.replace("_", "-")}
            )
            for name in (
                "capture_operation",
                "initial_operation",
                "baseline_operation",
                "comparison_operation",
                "equivalence_operation",
            )
        }
        d = TaskInitializationPlan.model_validate(
            template.model_copy(
                update={
                    "scope": c["scope"],
                    "browser_spec_ref": c["initial_selection"].browser_spec_ref,
                    "browser_acquisition": start,
                    "actor": template.actor.model_copy(
                        update={
                            "model_allocation": template.actor.model_allocation.model_copy(
                                update={"owner": c["scope"].owner}
                            )
                        }
                    ),
                    **stages,
                }
            )
        )
        engine, page = b.channels[0].engine, Page(c["public"])
        page.url = c["public"].start_url
        passive_calls: list[str] = []

        def capture(
            request: BrowserCaptureRequest, *, control: OperationControl
        ) -> BrowserCaptureResult:
            control.checkpoint()
            request.check_readout(
                b.spec.configuration.spec, session.engine.last_readout
            )
            passive_calls.append(request.collector_id)
            result = BrowserCaptureResult(
                request_sha256=request.digest,
                captured_at=datetime.now(timezone.utc),
                private_result=ShoppingCategoryPageCollector().collect(
                    page, request.collector_id, request.collector_version, control
                ),
            )
            engine.last_capture = result
            return result

        monkeypatch.setattr(engine, "last_capture", None, raising=False)
        monkeypatch.setattr(engine, "capture_page", capture, raising=False)
        cap_authority = CaptureAuthority(store)
        cap_authority.denied = fault == "capture-denied"
        initial_authority = InitialAuthority(c["initial_selection"])

        def records(intent: EvidenceRef, result: EvidenceRef) -> Any:
            assert store.read(intent, guard()) and store.read(result, guard())
            return category_initial_observations(
                store, b.controls, c["preparations"], initial_authority
            )

        measurement = CapturedTaskInitialMeasurements(
            d,
            owner,
            store,
            b.controls,
            cap_authority,
            records,
            collector_id="shopping-category-navigation-page",
            collector_version="1",
        )
        original_put = store.put

        def put(
            raw: bytes,
            metadata: EvidenceMetadata,
            control: OperationControl | None = None,
            *,
            exchange_id: str | None = None,
        ) -> EvidenceRef:
            target = (
                "browser-capture-result/1"
                if fault == "result-write"
                else "initial-state-checks/1"
            )
            if (
                fault in ("result-write", "initial-write")
                and metadata.content_schema == target
            ):
                raise OSError("category initial publication fixture")
            return EvidenceRef.model_validate(
                original_put(raw, metadata, control, exchange_id=exchange_id)
            )

        class Cancel:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "category-initial-fixture")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        first_return = session.last_return_ref
        first_observation = session.observation_ref
        with monkeypatch.context() as writes:
            writes.setattr(store, "put", put)
            if fault == "none":
                ref = measurement.record(c["initial_selection"], guard())
                actual = InitialStateChecks.model_validate_json(
                    store.read(ref, guard())
                )
                original = InitialStateChecks.model_validate_json(
                    store.read(c["initial_checks_ref"], guard())
                )
                assert actual.operation == d.initial_operation
                assert (
                    actual.model_copy(update={"operation": original.operation})
                    == original
                )
                assert initial_authority.calls == 2
            else:
                expected = (
                    OperationStopped
                    if fault == "cancel"
                    else PermissionError if fault == "capture-denied" else OSError
                )
                with pytest.raises(expected) as caught:
                    measurement.record(
                        c["initial_selection"],
                        Cancel() if fault == "cancel" else guard(),
                    )
                if fault != "cancel":
                    assert getattr(caught.value, "capture_intent_reference") is not None
                    assert measurement.capture is not None
                    if fault == "result-write":
                        assert (
                            getattr(caught.value, "capture_returned_result") is not None
                        )
                        assert getattr(caught.value, "capture_result_reference") is None
                    if fault == "initial-write":
                        assert (
                            getattr(caught.value, "capture_result_reference")
                            is not None
                        )
        assert (
            session.observation_ref == first_observation
            and session.last_return_ref == first_return
        )
        assert engine.calls == ["start"] and page.visits == []
        assert passive_calls == (
            []
            if fault in ("cancel", "capture-denied")
            else ["shopping-category-navigation-page"]
        )
        if fault != "cancel":
            with pytest.raises(DispatchAlreadyCommitted):
                measurement.record(c["initial_selection"], guard())
        assert owner.phase == "open"

    def closed(c: dict[str, Any]) -> None:
        assert c["browser_owner"].phase == "closed"
        assert c["browser_owner"].closed is not None
        assert c["closure"].status == "closed"

    raw, _, public = originals[0]
    prepared_family_case(
        tmp_path,
        node_path,
        monkeypatch,
        "none",
        category=(raw, public),
        on_ready=ready,
        on_closed=closed,
        retain_browser=True,
    )
