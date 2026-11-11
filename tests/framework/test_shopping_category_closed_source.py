"""Complete original category graph with explicit synthetic physical/native rights."""

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.closed_source_read_bindings import (
    bind_closed_source_read,
)
from lab_generate_skill.bootstrap.shopping_category_closed_source import (
    closed_category_source_contexts,
)
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureRequest,
    BrowserCaptureResult,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    assemble_public_context,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.sites.shopping.navigation_page_capture import (
    ShoppingCategoryPageCollector,
)
from shopping_category_browser_fixtures import Page
from shopping_prepared_family_fixtures import prepared_family_case
from shopping_category_source_raw_fixtures import complete_unit_closed_raw
from preparation_record_fixtures import put
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault", ["none", "capture-missing", "native", "reset-missing", "resource-state"]
)
def test_original_category_full_closed_graph_recomputes_and_refuses_changed_dependencies(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    saved: dict[str, Any] = {}

    def ready(c: dict[str, Any]) -> None:
        saved.update(c)
        complete_unit_closed_raw(monkeypatch)
        browser, store = c["browser_case"], c["store"]
        request = BrowserCaptureRequest(
            scope=c["prepared"].scope,
            operation=browser.op.model_copy(
                update={"operation_id": "source-category-first-capture"}
            ),
            observation_sha256=c["session"].observation_ref.sha256,
            collector_id="shopping-category-navigation-page",
            collector_version="1",
        )
        intent = BrowserCaptureIntent(
            request=request,
            configuration_sha256=hashlib.sha256(
                browser.spec.configuration.model_dump_json().encode()
            ).hexdigest(),
        )
        page = Page(c["public"])
        page.url = c["public"].start_url
        result = BrowserCaptureResult(
            request_sha256=request.digest,
            captured_at=datetime.now(timezone.utc),
            private_result=ShoppingCategoryPageCollector().collect(
                page, request.collector_id, request.collector_version, guard()
            ),
        )
        saved["capture_intent_ref"], saved["capture_result_ref"] = put(
            store, intent
        ), put(store, result)

    def finished(c: dict[str, Any]) -> None:
        store, site, browser = c["store"], c["c"], saved["browser_case"]
        scope = c["scope"]
        op = OperationContext(
            operation_id="category-unit-source-context",
            run_id=scope.owner.run_id,
            owner_id=scope.owner.owner_id,
            deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
        )
        public = PublicConstructionContext(
            context_id=scope.context_id,
            task=c["public"],
            initial_observation_ref=saved["baseline"].observation_ref,
        )
        inputs = PublicContextInputs(
            context=public,
            context_ref=put(store, public, "public"),
            baseline_inputs=saved["baseline_inputs"],
            baseline=saved["baseline"],
            baseline_ref=put(store, saved["baseline"]),
            reset_inputs=c["reset_inputs"],
            reset=c["reset_receipt"],
            reset_ref=put(store, c["reset_receipt"]),
        )
        source = assemble_public_context(inputs, op)
        material = ClosedCategoryNavigationReadMaterial(
            context_ref=put(store, source),
            environment_ref=c["selection_ref"],
            reset_ref=c["reset_ref"],
            initial=saved["initial_selection"],
            capture_intent_ref=saved["capture_intent_ref"],
            capture_result_ref=saved["capture_result_ref"],
            site=site.spec,
            browser=browser.spec,
            site_record=site.journal.read(site.spec.token, site.op),
            browser_record=browser.journal.read(browser.spec.token, browser.op),
        )
        assert material.site_record.state == material.browser_record.state == "closed"
        if fault == "resource-state":
            bad = material.model_dump()
            bad["site_record"]["events"] = bad["site_record"]["events"][:-1]
            with pytest.raises(ValueError):
                ClosedCategoryNavigationReadMaterial.model_validate(bad)
            return
        if fault == "native":
            selected = material.browser.configuration.initialization.model_copy(
                update={"native_contract_sha256": "f" * 64}
            )
            material = material.model_copy(
                update={
                    "browser": material.browser.model_copy(
                        update={
                            "configuration": material.browser.configuration.model_copy(
                                update={"initialization": selected}
                            )
                        }
                    )
                }
            )
        elif fault == "reset-missing":
            ref = material.reset_ref.model_copy(
                update={"sha256": "f" * 64, "uri": "cas://sha256/" + "f" * 64}
            )
            material = material.model_copy(update={"reset_ref": ref})
        original = store.read

        def read(reference: Any, control: Any = None) -> bytes:
            if fault == "capture-missing" and reference == material.capture_result_ref:
                raise EvidenceIntegrityError("Unit original first capture unavailable")
            raw: bytes = original(reference, control=control)
            assert type(raw) is bytes
            return raw

        monkeypatch.setattr(store, "read", read)

        def no_write(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("Closed source attempted publication or native retry")

        monkeypatch.setattr(store, "put", no_write)
        if fault == "none":
            reader = closed_category_source_contexts(material, store, site.controls, op)
            assert reader.load_context(material.context_ref, op) == source
            compiled = bind_closed_source_read(material).contexts(
                store, site.controls, op
            )
            assert compiled.load_context(material.context_ref, op) == source
        else:
            expected = {
                "native": OwnershipConflict,
                "reset-missing": EvidenceNotFound,
                "capture-missing": EvidenceIntegrityError,
            }[fault]
            with pytest.raises(expected):
                closed_category_source_contexts(
                    material, store, site.controls, op
                ).load_context(material.context_ref, op)

    prepared_family_case(
        tmp_path,
        node_path,
        monkeypatch,
        "none",
        category=(originals[0][0], originals[0][2]),
        on_ready=ready,
        on_finished=finished,
    )


@pytest.mark.parametrize("value", [None, {}, [], True])
def test_untyped_or_missing_closed_category_material_refuses_without_effects(
    value: Any,
) -> None:
    with pytest.raises(ValueError):
        ClosedCategoryNavigationReadMaterial.model_validate(value)
