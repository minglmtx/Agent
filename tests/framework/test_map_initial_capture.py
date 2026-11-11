"""Initial export has no page reads/actions/seal and preserves original complete facts."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.map_initial_capture import MapInitialCapture
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.sites.map.browser_capture import MapBrowserCapture
from lab_generate_skill.sites.map.browser_initialization import (
    MapNativeBrowserInitializer,
)
from lab_generate_skill.sites.map.initial_readiness_rules import original_readiness
from map_browser_initialization_fixtures import (
    Clock,
    Sink,
    Page,
    selection,
    public_task,
)
from map_browser_collection_fixtures import CollectionCase
from test_map_initialization_collection import select_native
from test_map_browser_collection import capture
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.adapters.map_artifacts.browser_files import (
    OriginalMapBrowserFiles,
)
from test_browser_resource import enter, inspect
from test_slurm_commands import guard


def ready_fact() -> bytes:
    clock, sink = Clock(), Sink()
    init = MapNativeBrowserInitializer(selection(), clock, sink)
    init.setup(Page(clock), public_task(), guard())
    assert init.last_fact is not None
    return init.last_fact


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "early",
        "late",
        "bool",
        "nonfinite",
        "busy",
        "loading",
        "not-ready",
        "no-route",
        "invisible",
        "geo-disagree",
        "long-disagree",
        "coordinates",
        "missing",
        "extra",
        "task",
        "claim",
        "duplicate",
        "empty",
        "null",
        "list",
        "bad-type",
    ],
)
def test_original_readiness_full_fact_rules(fault: str) -> None:
    raw: Any = ready_fact()
    v = json.loads(raw)
    if fault == "early":
        v["stable_seconds"] = 0.749
    if fault == "late":
        v["stable_seconds"] = 45.001
    if fault == "bool":
        v["stable_seconds"] = True
    if fault == "nonfinite":
        v["stable_seconds"] = float("inf")
    if fault in ("busy", "loading"):
        v["native_readiness"][fault] = True
    if fault == "not-ready":
        v["native_readiness"]["ready"] = False
    if fault == "no-route":
        v["native_readiness"]["directionsContent"] = False
    if fault == "invisible":
        v["native_view"]["map_visible"] = False
    if fault == "geo-disagree":
        v["native_view"]["native_geo_uri"] = "geo:40.78,-73.97?z=14"
    if fault == "long-disagree":
        v["native_view"]["native_long_link"] = "/#map=14/40.78/-73.97"
    if fault == "coordinates":
        v["native_view"]["native_long_link"] = v["native_readiness"]["long"] = (
            "/#map=14/40.78/-73.97"
        )
    if fault == "missing":
        v.pop("native_view")
    if fault == "extra":
        v["other"] = 0
    if fault == "task":
        v["public_task"]["goal"] = "other"
    if fault == "claim":
        v["new_observation_created"] = True
    raw = json.dumps(v, sort_keys=True, ensure_ascii=False).encode()
    if fault == "duplicate":
        raw = b'{"stable_seconds":0,' + raw[1:]
    if fault == "empty":
        raw = b""
    if fault == "null":
        raw = b"null"
    if fault == "list":
        raw = b"[]"
    if fault == "bad-type":
        raw = None
    if fault == "none":
        assert (
            original_readiness(raw, selection(), public_task())["stable_seconds"]
            >= 0.75
        )
    else:
        with pytest.raises((ValueError, TypeError, EvidenceIntegrityError)):
            original_readiness(raw, selection(), public_task())


def test_initial_capture_keeps_original_active_collection_then_actions_and_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = CollectionCase(tmp_path, monkeypatch)
    select_native(c)
    with enter(c.resource) as browser:
        assert c.engine is not None and isinstance(
            c.engine.collector, MapBrowserCapture
        )
        collector = c.engine.collector
        assert c.collector is not None and c.collector.native is not None
        first = c.engine.last_readout
        calls = list(c.calls)
        reads = c.page.reads
        assert first is not None
        recorder, request = capture(c, browser)
        request = request.model_copy(
            update={
                "collector_id": "map-initial-readiness",
                "operation": request.operation.model_copy(
                    update={"operation_id": "initial-private-capture"}
                ),
            }
        )
        recorder.capture(request, control=guard())
        assert recorder.result is not None
        proof = MapInitialCapture.model_validate_json(recorder.result.private_result)
        assert (
            c.engine.last_readout is first
            and c.calls == calls
            and c.page.reads == reads
        )
        assert (
            c.collector.state == "active"
            and not c.collector.native.requests.relay.physical_closed
        )
        assert isinstance(c.collector.files, OriginalMapBrowserFiles)
        assert (
            c.collector.files.writer.state == "active"
            and c.collector.files.writer.handle is None
        )
        assert not (Path(c.plan.private_root) / "published/manifest.json").exists()
        assert list((Path(c.plan.private_root) / "published").iterdir()) == []
        assert proof.readiness_json.encode() == collector.initialization.last_fact
        assert (
            proof.readout_sha256
            == hashlib.sha256(first.model_dump_json().encode()).hexdigest()
        )
        with pytest.raises(InvalidTransition):
            collector.collect(c.page, "map-initial-readiness", "1", guard())
        browser.step(
            BrowserAction(
                action_id="click",
                protocol_id="browsergym-highlevel-v1",
                name="click",
                payload="click('a')",
            ),
            c.resource.op.model_copy(update={"operation_id": "actor-action"}),
            control=guard(),
        )
        terminal, request = capture(c, browser)
        terminal.capture(request, control=guard(30))
        assert (
            c.engine.last_readout is not None
            and c.engine.last_readout.observation.sequence == 1
        )
        assert (
            c.collector.state == "published"
            and c.collector.native.requests.relay.physical_closed
        )
    assert inspect(c.resource).state == "closed"


@pytest.mark.parametrize(
    "fault", ["selector", "version", "page", "thread", "cancel", "late", "receipt"]
)
def test_initial_export_boundaries_do_not_create_another_return(
    fault: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = CollectionCase(tmp_path, monkeypatch)
    select_native(c)
    with enter(c.resource) as browser:
        assert c.engine is not None and isinstance(
            c.engine.collector, MapBrowserCapture
        )
        collector = c.engine.collector
        if fault == "late":
            browser.step(
                BrowserAction(
                    action_id="click",
                    protocol_id="browsergym-highlevel-v1",
                    name="click",
                    payload="click('a')",
                ),
                c.resource.op.model_copy(update={"operation_id": "acted"}),
                control=guard(),
            )
        if fault == "receipt":
            assert collector.initialization.reference is not None
            collector.initialization.reference = (
                collector.initialization.reference.model_copy(
                    update={"sha256": "f" * 64}
                )
            )
        first = c.engine.last_readout
        reads = c.page.reads
        calls = list(c.calls)

        class Cancel:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "initial-map-capture")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        with pytest.raises(
            (ValueError, OwnershipConflict, InvalidTransition, OperationStopped)
        ):
            if fault == "thread":
                with ThreadPoolExecutor() as pool:
                    pool.submit(
                        collector.collect, c.page, "map-initial-readiness", "1", guard()
                    ).result()
            else:
                collector.collect(
                    object() if fault == "page" else c.page,
                    "other" if fault == "selector" else "map-initial-readiness",
                    "2" if fault == "version" else "1",
                    Cancel() if fault == "cancel" else guard(),
                )
        assert (
            c.engine.last_readout is first
            and c.page.reads == reads
            and c.calls == calls
        )
