"""Current selected callback -> relay -> file evidence and unique return binding."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
from typing import Any
import pytest
from lab_generate_skill.sites.map.native_route_request import (
    selected_bounds,
    private_headers,
)
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from map_route_fixtures import collection, Route, readout
from map_http_fixtures import http_fixture
from test_map_native_relay import get
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "method,kind,query",
    [
        ("POST", "xhr", "bbox=0,0,0.5,0.5"),
        ("GET", "document", "bbox=0,0,0.5,0.5"),
        ("GET", "fetch", "bbox=0,0,0.5,0.5"),
        ("GET", "xhr", "other=1"),
        ("GET", "xhr", "bbox=0,0,0.5,0.5&extra=1"),
        ("GET", "xhr", "bbox=0,0,0.5,0.5&bbox=0,0,0.5,0.5"),
    ],
)
def test_non_mapdata_request_stays_original(
    tmp_path: Path, method: str, kind: str, query: str
) -> None:
    c, w, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    c.attach(page, spec, guard())
    try:
        route = Route(c.relay.origin, method=method, kind=kind, query=query)
        page.handler(route)
        assert (
            route.calls == [{}]
            and not route.aborts
            and not c.requests
            and not c.relay.requests
        )
    finally:
        c.close(guard())


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:2/api/0.6/map?bbox=0,0,0.5,0.5",
        "http://127.0.0.1:1/api/0.6/notes?bbox=0,0,0.5,0.5",
        "http://127.0.0.1:1/api/0.6/map?bbox=0,0,0.5,0.5#fragment",
    ],
)
def test_other_origin_path_or_fragment_is_not_selected(url: str) -> None:
    assert selected_bounds("http://127.0.0.1:1", url, "GET", "xhr") is None


@pytest.mark.parametrize("value", [None, 1, {}, []])
def test_wrong_request_metadata_type_rejected(value: Any) -> None:
    with pytest.raises(ValueError):
        selected_bounds("http://127.0.0.1:1", value, "GET", "xhr")
    if value == {}:
        assert private_headers(value) == {"referer": ""}
    else:
        with pytest.raises(ValueError):
            private_headers(value)


def test_actual_native_relay_from_callback_and_unique_readouts(tmp_path: Path) -> None:
    with http_fixture("batch") as server:
        c, w, a, page, spec = collection(tmp_path, server.origin)
        c.attach(page, spec, guard())
        try:
            initial = readout(spec, 0)
            c.observe(page, initial, guard())
            route = Route(server.origin)
            page.handler(route)
            assert len(route.calls) == 1 and not route.aborts and not server.calls
            headers = route.calls[0]["headers"]
            assert headers == {"accept": "application/xml", "referer": ""}
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(get, route.calls[0]["url"], server.origin)
                final = readout(spec, 1, terminal=True)
                c.observe(page, final, guard(20))
                assert c.state == "terminal_pending" and c.finish_record is None
                c.finish(guard(20))
                assert future.result(timeout=3)[0] == 200
            assert c.readouts == [initial, final] and c.last_readout is final
            assert (
                len(server.calls) == 3
                and page.renderer_waits == 1
                and c.state == "terminal"
            )
            c.finish(guard())
            with pytest.raises(InvalidTransition):
                c.before_action(guard())
        finally:
            c.close(guard())
        c.close(guard())
        assert c.relay.physical_closed and page.unroutes == 1
    h = w.seal(guard())
    r = MapArtifactReader(w.plan, tmp_path, a)
    actual = json.loads(r.read(h, "request-0-browser-start.json", guard()))
    assert (
        actual["actual_url"] == route.request.url
        and actual["last_unique_observation_sequence"] == 0
    )
    captured = json.loads(r.read(h, "map-observation-1.json", guard()))
    assert captured["readout"] == final.model_dump(mode="json") and captured[
        "request_ids_seen"
    ] == ["request-0"]
    assert not json.loads(r.read(h, "map-process-close.json", guard()))[
        "task_success_or_admission_claim"
    ]


def test_explicit_limit_finish_does_not_require_terminal_action(tmp_path: Path) -> None:
    c, _, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    c.attach(page, spec, guard())
    c.observe(page, readout(spec, 0), guard())
    c.finish(guard())
    c.finish(guard())
    assert len(c.readouts) == 1 and page.waits == page.renderer_waits == 0
    with pytest.raises(InvalidTransition):
        c.before_action(guard())
    c.close(guard())


@pytest.mark.parametrize("fault", ["dictionary", "invalid-contract"])
def test_only_original_validated_readout_object_can_be_recorded(
    tmp_path: Path, fault: str
) -> None:
    c, w, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    c.attach(page, spec, guard())
    original = readout(spec, 0)
    invalid: Any = (
        original.model_dump()
        if fault == "dictionary"
        else original.model_copy(update={"environment_reward": True})
    )
    try:
        with pytest.raises((TypeError, ValueError)):
            c.observe(page, invalid, guard())
        assert c.last_readout is None and not c.readouts
        assert not (w.working / "map-observation-0.json").exists()
    finally:
        c.close(guard())


@pytest.mark.parametrize("fault", ["continue", "invalid-bbox", "duplicate"])
def test_callback_unknown_preserves_unique_return_without_replay(
    tmp_path: Path, fault: str
) -> None:
    with http_fixture() as server:
        c, w, _, page, spec = collection(tmp_path, server.origin)
        c.attach(page, spec, guard())
        route = Route(
            server.origin,
            query="bbox=" if fault == "invalid-bbox" else "bbox=0,0,0.5,0.5",
            fault="continue" if fault == "continue" else "",
        )
        page.handler(route)
        if fault == "duplicate":
            page.handler(route)
        assert c.errors and c.state == "failed" and route.aborts == 1
        if fault == "invalid-bbox":
            rejected = json.loads(
                (w.working / "request-0-browser-start.json").read_text()
            )
            assert rejected["actual_url"] == route.request.url
            assert rejected["requested_bbox_strings"] == [""]
            assert not c.relay.requests
        original = readout(spec, 0)
        with pytest.raises(EvidenceIntegrityError):
            c.observe(page, original, guard())
        assert c.last_readout is original and c.readouts == [original]
        assert json.loads((w.working / "map-observation-0.json").read_text())[
            "readout"
        ] == original.model_dump(mode="json")
        with pytest.raises(InvalidTransition):
            c.observe(page, original, guard())
        with pytest.raises(InvalidTransition):
            c.before_action(guard())
        assert not server.calls
        c.close(guard())


@pytest.mark.parametrize("fault", ["route", "unroute"])
def test_partial_attach_or_detach_still_closes_original_relay(
    tmp_path: Path, fault: str
) -> None:
    c, _, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    page.fault = fault
    if fault == "route":
        with pytest.raises(OSError):
            c.attach(page, spec, guard())
        c.close(guard())
    else:
        c.attach(page, spec, guard())
        with pytest.raises(BaseExceptionGroup):
            c.close(guard())
        with pytest.raises(BaseExceptionGroup):
            c.close(guard())
    assert c.relay.physical_closed and page.unroutes == 1


@pytest.mark.parametrize("fault", ["page", "origin", "scope"])
def test_wrong_attach_rejected_before_server(tmp_path: Path, fault: str) -> None:
    c, _, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    if fault == "page":
        page.url = "http://127.0.0.1:1/"
    elif fault == "origin":
        spec = spec.model_copy(
            update={
                "task": spec.task.model_copy(
                    update={"start_url": "http://127.0.0.1:2/"}
                )
            }
        )
    else:
        spec = spec.model_copy(
            update={"scope": spec.scope.model_copy(update={"context_id": "wrong"})}
        )
    with pytest.raises(OwnershipConflict):
        c.attach(page, spec, guard())
    assert c.relay.server is None and page.routes == 0


def test_lost_observation_persistence_cannot_be_replayed(tmp_path: Path) -> None:
    c, w, a, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    c.attach(page, spec, guard())
    a.denied = True
    original = readout(spec, 0)
    with pytest.raises(PermissionError):
        c.observe(page, original, guard())
    assert c.last_readout is original and not c.readouts
    a.denied = False
    with pytest.raises(InvalidTransition):
        c.observe(page, original, guard())
    assert not (w.working / "map-observation-0.json").exists()
    c.close(guard())


def test_relay_cleanup_record_failure_stays_unknown_on_repeat(tmp_path: Path) -> None:
    c, w, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    attempts = []

    class Sink:
        def retain(
            self, name: str, data: bytes, control: OperationControl
        ) -> ReleaseFile:
            if name.endswith("never-requested.json"):
                attempts.append(name)
                raise OSError("original closure record unavailable")
            return w.retain(name, data, control)

    c.relay.sink = Sink()
    c.attach(page, spec, guard())
    page.handler(Route(c.relay.origin))
    with pytest.raises(BaseExceptionGroup):
        c.close(guard())
    assert c.relay.physical_closed and c.relay.state == "quarantined"
    with pytest.raises(BaseExceptionGroup):
        c.close(guard())
    assert len(attempts) == 1 and c.relay.state == "quarantined"


@pytest.mark.parametrize("retention_failure", [False, True])
@pytest.mark.parametrize("terminal", [False, True])
def test_existing_pending_timeout_and_retention_error_preserved(
    tmp_path: Path, retention_failure: bool, terminal: bool
) -> None:
    c, w, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")

    class Sink:
        def retain(
            self, name: str, data: bytes, control: OperationControl
        ) -> ReleaseFile:
            if retention_failure and name == "map-existing-pending-finish.json":
                raise OSError("terminal record unavailable")
            return w.retain(name, data, control)

    c.relay.sink = Sink()
    c.attach(page, spec, guard())
    c.observe(page, readout(spec, 0), guard())
    page.handler(Route(c.relay.origin))
    if terminal:
        c.observe(page, readout(spec, 1, terminal=True), guard())
        assert c.state == "terminal_pending"
    try:
        if retention_failure:
            with pytest.raises(BaseExceptionGroup) as caught:
                c.finish(guard(0.03))
            assert len(caught.value.exceptions) == 2
            assert isinstance(caught.value.exceptions[0], OperationStopped)
            assert caught.value.exceptions[0].reason_code == "DEADLINE_EXCEEDED"
            assert isinstance(caught.value.exceptions[1], OSError)
        else:
            with pytest.raises(OperationStopped) as stopped:
                c.finish(guard(0.03))
            assert stopped.value.reason_code == "DEADLINE_EXCEEDED"
            retained = json.loads(
                (w.working / "map-existing-pending-finish.json").read_text()
            )
            assert (
                not retained["passed"] and not retained["original_deadlines_extended"]
            )
        assert c.state == "failed" and not next(iter(c.relay.requests.values())).started
        with pytest.raises(InvalidTransition):
            c.finish(guard())
    finally:
        c.close(guard())
    assert c.relay.physical_closed


def test_duplicate_unique_readout_cannot_write_again(tmp_path: Path) -> None:
    c, w, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    c.attach(page, spec, guard())
    original = readout(spec, 0)
    c.observe(page, original, guard())
    before = list(w.files)
    try:
        with pytest.raises(OwnershipConflict):
            c.observe(page, original, guard())
        assert (
            w.files == before
            and c.readouts == [original]
            and c.last_readout is original
        )
    finally:
        c.close(guard())


def test_invalid_headers_retain_request_descriptor_before_rejection(
    tmp_path: Path,
) -> None:
    c, w, _, page, spec = collection(tmp_path, "http://127.0.0.1:1")
    c.attach(page, spec, guard())
    route = Route(c.relay.origin)
    route.request.headers = {"accept": None}
    try:
        page.handler(route)
        assert c.state == "failed" and route.aborts == 1 and not route.calls
        retained = json.loads((w.working / "request-0-browser-start.json").read_text())
        assert retained["actual_url"] == route.request.url
        assert not c.relay.requests
    finally:
        c.close(guard())
