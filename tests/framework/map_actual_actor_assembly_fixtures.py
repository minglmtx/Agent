"""Actual Map callbacks/orchestration, with explicit model/native/Page/kernel doubles."""

from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.adapters.sites.resource import RegisteredSite


from pathlib import Path
from actor_context_projection_fixtures import actor_projection_case
from typing import Any
import pytest
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureIntent,
    BrowserCaptureResult,
)
from lab_generate_skill.sites.map.tasks.overlay_recovery import OverlayObserved
from lab_generate_skill.sites.map.page_capture import PAGE_HEALTH_PROGRAM
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.map_reference_selection import MapReferenceSelection
from lab_generate_skill.sites.map.native_bounds import Bounds
from lab_generate_skill.ports.lifecycle import OperationControl
from map_terminal_request_fixtures import Requests
from map_evaluation_capture_fixtures import database_body
from map_task_operations_native import execute as execute_operation
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualified_source_native import MapQualifiedSource
from map_browser_collection_fixtures import CollectionCase
from map_initial_records_fixtures import InitialCase
from map_prepared_records_fixtures import PreparedMapCase
from map_actor_trace_fixtures import execute_actor
from map_actor_callbacks import MapActorCallbacks
from map_site_engineering_authority import MapEngineeringAuthority
from map_source_lifecycle_native import run
from map_overlay_capture_fixtures import full_surface_fixture
from initial_observation_fixtures import Authority
from source_task_hooks import SourceTaskHooks
from test_map_page_health import health
from test_slurm_commands import guard
import source_actor_callbacks
from map_source_native_boundary_fixtures import source_native_boundary
from lab_generate_skill.domain.site_capture import SiteCaptureRequest


def run_combination(
    c: RegisteredMapCase,
    source: MapQualifiedSource,
    browsers: list[CollectionCase],
    patch: pytest.MonkeyPatch,
    *,
    mode: str = "no-request",
    terminal: bool = False,
) -> dict[str, Any]:
    full_surface_fixture(patch)
    requests = None if mode == "no-request" else Requests(patch, mode)
    pending_bounds: Bounds | None = None
    queries: list[tuple[str, ...]] = []
    original_commands = c.case.commands.run

    def command(argv: tuple[str, ...], control: OperationControl) -> bytes:
        if "runner" not in argv:
            return original_commands(argv, control)
        assert pending_bounds is not None
        body = database_body(pending_bounds)  # Already checked by original parser.
        queries.append(argv)
        path = (
            Path(c.case.spec.state_root("frontend"))
            / "native-reference-layer-final-0"
            / "osm-expanded-layer-final-0.json"
        )
        assert path.parent.joinpath("reference.rb").is_file()
        with path.open("xb") as output:
            output.write(body)
        path.chmod(0o400)
        return b"explicit native Rails output double; full bytes retained"

    patch.setattr(c.case.commands, "run", command)
    captured: list[str] = []

    def before_capture(request: SiteCaptureRequest) -> None:
        nonlocal pending_bounds
        if request.collector_id == "map-native-reference":
            assert request.selection_ref is not None
            pending_bounds = MapReferenceSelection.model_validate_json(
                c.resource.evidence.read(request.selection_ref, control=guard())
            ).bounds

    source_native_boundary(c, source, patch, captured, before_capture)

    def actor(
        s: Any,
        browser: Any,
        session: Any,
        *args: Any,
        max_interactions: int,
        context_policy: Any,
        projection: Any = None,
    ) -> Any:
        assert max_interactions == 16
        assert context_policy.role == "actor" and projection is None
        assert s is source and browser is browsers[0].resource
        n, store, b = source.native, c.resource.evidence, browsers[0]
        assert n.request is not None and n.result is not None
        evidence = source.initial_evidence
        assert isinstance(n.records, EvidencePreparationRecords)
        assert isinstance(source.site, RegisteredSite)
        prepared = PreparedMapCase(
            n.request,
            n.result,
            source.saved["snapshot"],
            OverlayObserved.model_validate_json(n.result.private_result),
            source.environment,
            n.records,
            source.publication,
        )
        selected = source.saved["initial_selection"]
        case = InitialCase(
            source.site,
            b,
            session,
            prepared,
            selected,
            source.initial_records(Authority(selected)),
            evidence,
            BrowserCaptureIntent.model_validate_json(store.read(evidence.intent_ref)),
            BrowserCaptureResult.model_validate_json(store.read(evidence.result_ref)),
            browser.op,
        )
        # A terminal return seals callback registration. Register the original
        # fixture request while the browser is active, never after termination.
        if terminal and requests is not None:
            requests(case)
        trace_ref, snapshot_ref, trace, snapshot = execute_actor(
            c, case, terminal=terminal
        )
        if not terminal and requests is not None:
            requests(case)
        b.participant = "controller"
        old_browser = session.engine.capture_page

        def browser_capture(*a: Any, **kw: Any) -> Any:
            b.participant = "worker"
            try:
                return old_browser(*a, **kw)
            finally:
                b.participant = "controller"

        patch.setattr(session.engine, "capture_page", browser_capture)
        evaluate = b.page.evaluate
        patch.setattr(
            b.page,
            "evaluate",
            lambda program, args=None: (
                health(b.page.url)
                if program == PAGE_HEALTH_PROGRAM
                else evaluate(program, args)
            ),
        )
        return (
            dict(
                trace_ref=trace_ref.model_dump(mode="json"),
                trace_snapshot_ref=snapshot_ref.model_dump(mode="json"),
                verified_model_returns=1,
                generations=trace.generations,
                interactions=trace.interactions,
            ),
            None,
        )

    patch.setattr(source_actor_callbacks, "execute_source_actor", actor)
    unit: Any = None  # Model resource arguments are not read by the explicit double.
    callbacks = MapActorCallbacks(
        unit,
        unit,
        unit,
        c.workspace / "unused-model-root",
        context_policy=actor_projection_case().policy,
    )
    hooks = SourceTaskHooks(
        c.scope.owner,
        c.resource.evidence,
        ("click", "send_msg_to_user"),
        callbacks.execute,
        callbacks.evaluate,
    )
    facts: dict[str, Any] = {}
    try:
        run(source, hooks, c.workspace, patch, facts)
        if callbacks.errors:
            import traceback

            for error in callbacks.errors:
                traceback.print_exception(error)
        assert callbacks.errors == [], callbacks.facts
        assert callbacks.facts["judgment"]["evaluation"]["status"] == "failure"
        assert callbacks.facts["judgment"]["independent_readonly_equal"] is True
        assert captured == (
            ["map-overlay-state"]
            if requests is None
            else ["map-native-reference", "map-overlay-state"]
        )
        assert len(queries) == int(requests is not None)
        assert facts["qualified_source"]["reset_status"] == "safe"
        assert facts["prepared_browser"]["complete_baseline"]
        assert len(source.saved["map_references"]) == int(requests is not None)
        if requests is not None:
            assert source.saved["map_request_selection"]["eligible"][0][
                "response_kind"
            ] == ("adapted_union" if mode == "batch" else "native_200")
        before = len(c.case.commands.calls)
        with pytest.raises(OwnershipConflict):
            execute_operation(source, "restore", source.saved["snapshot_ref"])
        assert len(c.case.commands.calls) == before
        facts["judgment"] = callbacks.facts["judgment"]
        facts["configuration"] = c.resource.spec.model_dump(mode="json")
        facts["started"] = source.site.site.model_dump(mode="json")
        return facts
    finally:
        c.observer = "worker"
