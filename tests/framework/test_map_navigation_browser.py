"""All8 current Task/browser contract/passive capture/pure-rule/reset software path.

SQL, services, page and resource authority are explicit doubles. No Actor,
unique public Observation, real browser or source admission is claimed here.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.bootstrap.browser_engine import build_browser_engine
from lab_generate_skill.bootstrap.browser_initialization import browser_initializer
from lab_generate_skill.bootstrap.map_overlay_records import map_prepared_browser_checks
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.preparation import PreparedTask
from lab_generate_skill.sites.map.navigation_browser_initialization import (
    MapNavigationBrowserInitializer,
)
from lab_generate_skill.sites.map.navigation_browser_capture import (
    NavigationBrowserCapture,
)
from lab_generate_skill.sites.map.navigation_initial_evidence import (
    NavigationInitialReadiness,
)
from lab_generate_skill.sites.map.navigation_page_schema import NavigationPageHealth
from lab_generate_skill.sites.map.navigation_rules import navigation_outcome
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_navigation_browser_fixtures import selection, Page, Clock, CancelledControl
from map_navigation_group_cases import MEMBERS, SOURCES
from map_qualification_fixtures import qualified, restore
from map_navigation_prepared_fixtures import NavigationPreparedCase
from map_registered_worker_fixtures import RegisteredMapCase
from browsergym_fixtures import spec, LoopbackAuthority
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_site_resource import inspect
from test_slurm_commands import guard


@pytest.mark.parametrize("source,target,heading", MEMBERS)
def test_each_member_current_registered_preparation_binding_browser_capture_original_rule_and_restore(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    target: str,
    heading: str,
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    try:
        with qualified(c, monkeypatch) as q:
            p = q.preparation
            assert isinstance(p, NavigationPreparedCase) and isinstance(
                c.private, NavigationSpec
            )
            c.observer = "controller"
            try:
                prepared = p.records.load(p.publication, p.request.operation)
                selected = MapNavigationInitialization(
                    endpoint=q.live.site.instance.endpoint,
                    prepared_ref=p.publication.prepared_ref,
                    site_ref=put(c.resource.evidence, q.live.site),
                    native_contract_sha256=c.private.native_contract_ref.sha256,
                )
                checks = map_prepared_browser_checks(
                    c.resource.evidence, c.configuration, q.live.site.instance
                )
                checks.check_prepared(
                    p.publication.selection.result_ref,
                    p.request,
                    selected,
                    c.configuration,
                    q.live.site.instance,
                    guard(),
                )
            finally:
                c.observer = "worker"
            base = spec(prepared.public_task.start_url)
            cfg = BrowserWorkerConfiguration(
                spec=base.model_copy(
                    update={"scope": c.scope, "task": prepared.public_task}
                ),
                initialization=selected,
                installation=c.configuration.installation,
                playwright_browsers_path="/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/playwright",
                library_directories=(),
            )
            clock = Clock()
            engine = build_browser_engine(
                cfg, LoopbackAuthority(), clock, worker_guard=None
            )
            assert engine.process_collector is None
            assert isinstance(engine.initializer, MapNavigationBrowserInitializer)
            assert isinstance(engine.collector, NavigationBrowserCapture)
            page = Page(clock)
            engine.initializer.setup(page, prepared.public_task, guard())
            init = NavigationInitialReadiness.model_validate_json(
                engine.collector.collect(page, "map-navigation-initial", "1", guard())
            )
            assert init.start_url == prepared.public_task.start_url
            assert page.calls[0] == "goto:" + prepared.public_task.start_url
            assert len([v for v in page.calls if v.startswith("goto:")]) == 1
            if source == SOURCES[-1]:
                assert init.native_view_json is None and page.arguments is None
            else:
                assert init.native_view_json is not None and init.stable_seconds >= 0.75
            # Explicit terminal control fixture, not an Actor action/result.
            page.url = selected.endpoint.rstrip("/") + target
            page.headings = [heading]
            terminal = NavigationPageHealth.model_validate_json(
                engine.collector.collect(
                    page, "map-navigation-page-health", "1", guard()
                )
            )
            outcome = navigation_outcome(
                c.private,
                terminal.original_page(),
                site_origin=selected.endpoint.rstrip("/"),
                runtime_error=False,
                selected_records_unchanged=True,
            )
            assert outcome.status == "success"
            assert len([v for v in page.calls if v.startswith("goto:")]) == 1
            with pytest.raises(InvalidTransition):
                engine.collector.collect(
                    page, "map-navigation-page-health", "1", guard()
                )
            assert c.worker is not None and c.worker.references is None
            # Browser closures in this module's existing qualifier are explicit
            # unit facts. Do not relabel this engine construction as real close.
            reset = restore(q)
            assert (
                q.qualifications.checks.reset(
                    reset, put(c.resource.evidence, reset), guard()
                ).health.status
                == "pass"
            )
        assert inspect(c.resource).state == "closed"
    finally:
        c.close_sockets()


@pytest.mark.parametrize(
    "fault",
    [
        "goto",
        "wait",
        "signal",
        "capture",
        "unknown-http",
        "cancel",
        "thread",
        "already-open",
    ],
)
def test_initial_failure_never_navigates_twice_or_claims_ready(fault: str) -> None:
    selected, public = selection(SOURCES[0])
    clock = Clock()
    page = Page(clock)
    initial = MapNavigationBrowserInitializer(selected, clock)
    page.fault = fault
    if fault == "unknown-http":
        page.status = None
    if fault == "already-open":
        page.url = public.start_url
    control = CancelledControl() if fault == "cancel" else guard()
    with pytest.raises(
        (
            ValueError,
            RuntimeError,
            OSError,
            TimeoutError,
            OperationStopped,
            OwnershipConflict,
        )
    ):
        if fault == "thread":
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(initial.setup, page, public, control).result()
        else:
            initial.setup(page, public, control)
    assert initial.fact is None
    assert len([v for v in page.calls if v.startswith("goto:")]) <= 1
    if initial.attempted:
        with pytest.raises(InvalidTransition):
            initial.setup(page, public, guard())


@pytest.mark.parametrize(
    "fault",
    [
        "unknown-selector",
        "version",
        "before-initial",
        "partial",
        "document-changed",
        "cancel",
    ],
)
def test_capture_boundaries_keep_unknown_or_refuse_without_repeat(fault: str) -> None:
    selected, public = selection(SOURCES[0])
    clock = Clock()
    page = Page(clock)
    initial = MapNavigationBrowserInitializer(selected, clock)
    initial.setup(page, public, guard())
    collector = NavigationBrowserCapture(initial)
    if fault == "unknown-selector":
        with pytest.raises(ValueError):
            collector.collect(page, "map-native-process", "1", guard())
        return
    if fault == "version":
        with pytest.raises(ValueError):
            collector.collect(page, "map-navigation-initial", "2", guard())
        return
    if fault == "before-initial":
        with pytest.raises(InvalidTransition):
            collector.collect(page, "map-navigation-page-health", "1", guard())
        return
    collector.collect(page, "map-navigation-initial", "1", guard())
    if fault in ("partial", "cancel"):
        page.fault = "capture"
        with pytest.raises((OSError, OperationStopped)):
            collector.collect(
                page,
                "map-navigation-page-health",
                "1",
                CancelledControl() if fault == "cancel" else guard(),
            )
        if fault == "partial":
            with pytest.raises(InvalidTransition):
                collector.collect(page, "map-navigation-page-health", "1", guard())
    else:
        page.fault = "document-changed"
        result = NavigationPageHealth.model_validate_json(
            collector.collect(page, "map-navigation-page-health", "1", guard())
        )
        assert (
            result.health.http_status is None
            and result.health.status_source == "document_changed"
        )


@pytest.mark.parametrize("source", [SOURCES[0], "058c211ed6572633b8e3"])
def test_only_whole_selected_subgroup_and_exact_contract_can_initialize(
    source: str,
) -> None:
    from map_navigation_fixtures import navigation_case

    c = navigation_case(source)
    selected, _ = selection(source)
    if source not in SOURCES:
        with pytest.raises(ValueError):
            selected.check_task(c.public)
    else:
        selected.check_task(c.public)
        with pytest.raises(ValueError):
            selected.model_copy(update={"native_contract_sha256": "f" * 64}).check_task(
                c.public
            )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        0,
        False,
        {},
        [],
        {"kind": "map_native_navigation", "endpoint": "http://127.0.0.1:1/"},
    ],
)
def test_invalid_navigation_contract_does_not_select_a_fallback(value: object) -> None:
    with pytest.raises(ValidationError):
        MapNavigationInitialization.model_validate(value)
