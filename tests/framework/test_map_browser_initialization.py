"""Selected original readiness before first observation, exact scripts and input gates."""

import ast
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.sites.map.browser_initialization import (
    MapNativeBrowserInitializer,
)
from lab_generate_skill.sites.map.native_view_scripts import READ, READINESS
from lab_generate_skill.sites.map.native_view_rules import native_zoom
from map_browser_initialization_fixtures import (
    Clock,
    Sink,
    Page,
    selection,
    public_task,
)
from map_database_original_oracle import ROOT
from test_slurm_commands import guard


def test_exact_original_scripts_and_selected_autopan_branch() -> None:
    tree = ast.parse((ROOT / "src/lab_generate_skill/map_view.py").read_text())
    values = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in ("READ", "READINESS")
    }
    assert READ == values["READ"] and READINESS == values["READINESS"]
    clock, sink = Clock(), Sink()
    page = Page(clock)
    init = MapNativeBrowserInitializer(selection(), clock, sink)
    init.setup(page, public_task(), guard())
    assert (
        page.arguments is not None
        and page.arguments["expectedCenter"] is None
        and page.arguments["expectedZoom"] is None
    )
    assert page.arguments["directions"] and page.arguments["routeRequest"]
    assert (
        page.calls.count("goto") == 1
        and page.calls.count("view") == 1
        and clock.elapsed >= 0.75
    )
    value = json.loads(sink.files["map-initial-readiness.json"])
    assert value["stable_seconds"] >= 0.75 and value["native_view"] == page.view
    assert (
        not value["new_observation_created"]
        and not value["task_success_or_admission_claim"]
    )
    assert init.reference is not None and init.error is None
    with pytest.raises(InvalidTransition):
        init.setup(page, public_task(), guard())
    assert page.calls.count("goto") == 1


@pytest.mark.parametrize(
    "fault",
    [
        "pending",
        "unstable",
        "wait",
        "goto",
        "redirect",
        "signal-type",
        "view-type",
        "link",
    ],
)
def test_readiness_wait_faults_retain_original_without_navigation_retry(
    fault: str,
) -> None:
    clock, sink = Clock(), Sink()
    page = Page(clock)
    page.fault = fault
    if fault == "signal-type":
        page.signal["ready"] = 1
    if fault == "view-type":
        page.view = []
    if fault == "link":
        page.view["native_long_link"] = "/#map=13/40.77/-73.97"
    init = MapNativeBrowserInitializer(selection(), clock, sink)
    if fault == "pending":
        init.setup(page, public_task(), guard())
        assert clock.elapsed >= 1.15 and init.reference is not None
    else:
        with pytest.raises(
            (TimeoutError, OSError, ValueError, OwnershipConflict)
        ) as caught:
            init.setup(page, public_task(), guard())
        assert init.error is caught.value and init.failure_ref is not None
        assert "map-initial-readiness.json" not in sink.files
        record = json.loads(sink.files["map-initial-readiness-failure.json"])
        assert type(caught.value).__name__ in record["error"]
        with pytest.raises(InvalidTransition):
            init.setup(page, public_task(), guard())
    assert page.calls.count("goto") == 1
    assert clock.elapsed <= 45.001


@pytest.mark.parametrize("fault", ["before", "after", "wrong"])
def test_private_retention_fault_blocks_initial_success_and_does_not_repeat(
    fault: str,
) -> None:
    clock, sink = Clock(), Sink()
    page = Page(clock)
    sink.fault = fault
    init = MapNativeBrowserInitializer(selection(), clock, sink)
    with pytest.raises(BaseExceptionGroup) as caught:
        init.setup(page, public_task(), guard())
    assert (
        len(caught.value.exceptions) == 2 and init.error is caught.value.exceptions[0]
    )
    with pytest.raises(InvalidTransition):
        init.setup(page, public_task(), guard())
    assert page.calls.count("goto") == 1
    assert ("map-initial-readiness.json" in sink.files) == (fault != "before")


def test_cancel_before_navigation_and_original_thread_only() -> None:
    class Stop:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "original-map")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    clock, sink = Clock(), Sink()
    page = Page(clock)
    init = MapNativeBrowserInitializer(selection(), clock, sink)
    with pytest.raises(OperationStopped):
        init.setup(page, public_task(), Stop())
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(init.setup, page, public_task(), guard()).result()
    assert page.calls == [] and sink.files == {} and not init.attempted


def test_cancel_during_stability_keeps_original_error_without_renewal_or_retry() -> (
    None
):
    clock, sink = Clock(), Sink()
    page = Page(clock)

    class CancelDuringWait:
        def checkpoint(self) -> float:
            if clock.elapsed >= 0.25:
                raise OperationStopped("CANCELLED", "original-map")
            return 0.25 - clock.elapsed

        def wait(self, seconds: float) -> None:
            clock.sleep(seconds)
            self.checkpoint()

    init = MapNativeBrowserInitializer(selection(), clock, sink)
    with pytest.raises(BaseExceptionGroup) as caught:
        init.setup(page, public_task(), CancelDuringWait())
    assert len(caught.value.exceptions) == 2
    assert all(isinstance(e, OperationStopped) for e in caught.value.exceptions)
    assert init.error is caught.value.exceptions[0]
    assert init.attempted and init.reference is None and init.failure_ref is None
    assert init.failure_fact is not None and b"CANCELLED" in init.failure_fact
    assert page.calls.count("goto") == 1 and "view" not in page.calls
    assert clock.elapsed == pytest.approx(0.25) and sink.files == {}
    with pytest.raises(InvalidTransition):
        init.setup(page, public_task(), guard())
    assert page.calls.count("goto") == 1


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        1,
        "http://127.0.0.1:1/",
        "http://localhost:18080/",
        "http://127.0.0.1:18080",
        "http://127.0.0.1:18080/path",
        "http://u@127.0.0.1:18080/",
    ],
)
def test_invalid_endpoints_rejected(value: Any) -> None:
    with pytest.raises(ValidationError):
        MapNativeInitialization.model_validate(
            selection().model_copy(update={"endpoint": value})
        )


@pytest.mark.parametrize("port", [1024, 65535])
def test_endpoint_boundaries_and_private_references(port: int) -> None:
    selected = selection(f"http://127.0.0.1:{port}/")
    selected.check_task(public_task(selected.endpoint))
    for name in ("prepared_ref", "site_ref"):
        ref = getattr(selected, name)
        with pytest.raises(ValueError):
            MapNativeInitialization.model_validate(
                selected.model_copy(
                    update={name: ref.model_copy(update={"visibility": "public"})}
                )
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("goal", "changed"),
        ("start_url", "http://127.0.0.1:18080/directions?route=other"),
        ("start_url", "http://127.0.0.1:18081/directions"),
        ("start_url", "http://127.0.0.1:18080/"),
    ],
)
def test_changed_public_input_rejects_before_first_effect(
    field: str, value: str
) -> None:
    clock, sink = Clock(), Sink()
    page = Page(clock)
    init = MapNativeBrowserInitializer(selection(), clock, sink)
    with pytest.raises(ValueError):
        init.setup(page, public_task().model_copy(update={field: value}), guard())
    assert not init.attempted and page.calls == []


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"map_visible": 1},
        {"map_visible": True, "native_geo_uri": "geo:91,0?z=15"},
    ],
)
def test_missing_illegal_native_view_rejected(value: Any) -> None:
    with pytest.raises(ValueError):
        native_zoom(value)
