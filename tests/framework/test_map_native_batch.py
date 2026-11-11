"""Known cap400 -> two actual clients -> exact full union, with durable facts."""

from copy import deepcopy
import hashlib
import threading
import time
from typing import Any, Callable
import pytest
from lab_generate_skill.sites.map import native_batch
from lab_generate_skill.sites.map.native_batch import complete_cap_response
from lab_generate_skill.sites.map.native_batch_records import NativeBatchError
from lab_generate_skill.sites.map.native_http import (
    NativeMapHttpClient,
    NativeResponse,
    NativeHttpReadError,
)
from lab_generate_skill.sites.map.native_bounds import Bounds, request_bounds
from lab_generate_skill.sites.map.native_xml import parse_adapted_xml
from map_xml_fixtures import ROOT, LEFT, xml
from map_http_fixtures import http_fixture

CAP = NativeResponse(
    400,
    "text/plain",
    b"You requested too many nodes (limit is 50000). Either request a smaller area, or use planet.osm\n",
)


class Saved:
    def __init__(self) -> None:
        self.rows: list[tuple[int, dict[str, Any], bytes | None]] = []

    def __call__(self, index: int, row: dict[str, Any], body: bytes | None) -> None:
        self.rows.append((index, deepcopy(row), body))


class ScriptedClient(NativeMapHttpClient):
    def __init__(self, response: Callable[[Bounds], NativeResponse]) -> None:
        super().__init__("http://127.0.0.1:18080")
        self.response = response
        self.calls: list[Bounds] = []

    def fetch(self, bounds: object, deadline: float) -> NativeResponse:
        value = request_bounds(bounds)
        self.calls.append(value)
        return self.response(value)


def normal(bounds: Bounds) -> NativeResponse:
    return NativeResponse(200, "application/xml; charset=utf-8", xml(bounds))


def test_actual_cap_request_and_two_http_children_complete_union() -> None:
    with http_fixture("batch") as server:
        deadline = time.monotonic() + 3
        source = NativeMapHttpClient(server.origin)
        original = source.fetch(ROOT, deadline)
        saved = Saved()
        clients = (
            NativeMapHttpClient(server.origin),
            NativeMapHttpClient(server.origin),
        )
        payload, summary = complete_cap_response(
            ROOT, original, clients, deadline=deadline, preserve=saved
        )
        assert original == NativeResponse(400, "application/xml", CAP.body)
        assert len(server.calls) == 3
        assert parse_adapted_xml(payload).objects["way"]["3"]["nodes"] == ["2", "1"]
        assert (
            summary["native_parent_http_status"] == 400
            and summary["native_children"] == 2
        )
        assert summary["maximum_independent_http_clients"] == 2
        assert not summary["original_absolute_deadline_renewed"]
        assert not summary["native_single_request_success"]
        assert any(index == 0 and body == CAP.body for index, _, body in saved.rows)
        assert [row["split_path"] for row in summary["requests"]] == [[], [0], [1]]
        assert all(c.socket is None and c.connection is None for c in clients)
        for index in (1, 2):
            writes = [(row, body) for i, row, body in saved.rows if i == index]
            assert writes[0][0]["status"] == "started" and writes[0][1] is None
            assert writes[-1][0]["body_complete"] and writes[-1][1]


def test_two_clients_actually_overlap_without_playwright_or_scope_change() -> None:
    barrier = threading.Barrier(2)

    def respond(bounds: Bounds) -> NativeResponse:
        barrier.wait(timeout=2)
        return normal(bounds)

    clients = (ScriptedClient(respond), ScriptedClient(respond))
    _, result = complete_cap_response(
        ROOT,
        CAP,
        clients,
        deadline=time.monotonic() + 3,
        preserve=Saved(),
        max_requests=3,
    )
    assert all(len(c.calls) == 1 for c in clients)
    assert all(result["coverage"].values())


@pytest.mark.parametrize(
    "response",
    [
        NativeResponse(200, "application/xml", xml()),
        NativeResponse(400, "text/plain", b"other error"),
        NativeResponse(500, "text/plain", CAP.body),
        None,
    ],
)
def test_only_exact_known_cap_permits_child_reads(response: NativeResponse) -> None:
    clients = (ScriptedClient(normal), ScriptedClient(normal))
    with pytest.raises(ValueError, match="cap400"):
        complete_cap_response(
            ROOT, response, clients, deadline=time.monotonic() + 1, preserve=Saved()
        )
    assert not any(c.calls for c in clients)


@pytest.mark.parametrize(
    "kind", ["non-cap", "wrong-bounds", "malformed", "wrong-schema", "transport"]
)
def test_child_failure_never_returns_partial_union_or_retries(kind: str) -> None:
    def respond(bounds: Bounds) -> NativeResponse:
        if bounds != LEFT:
            return normal(bounds)
        if kind == "transport":
            raise OSError("read interrupted")
        return {
            "non-cap": NativeResponse(503, "text/plain", b"unavailable"),
            "wrong-bounds": NativeResponse(200, "application/xml", xml()),
            "malformed": NativeResponse(200, "application/xml", b"<broken>"),
            "wrong-schema": NativeResponse(True, "application/xml", xml(LEFT)),
        }[kind]

    clients = (ScriptedClient(respond), ScriptedClient(respond))
    with pytest.raises(NativeBatchError) as caught:
        complete_cap_response(
            ROOT, CAP, clients, deadline=time.monotonic() + 1, preserve=Saved()
        )
    assert all(c.cancelled.is_set() for c in clients)
    calls = [bounds for c in clients for bounds in c.calls]
    assert len(calls) == len(set(calls)) and ROOT not in calls
    assert caught.value.ledger[0]["http_status"] == 400
    assert caught.value.__cause__ is not None


def test_preservation_failure_carries_known_body_and_keeps_first_error() -> None:
    saved = Saved()

    def preserve(index: int, row: dict[str, Any], body: bytes | None) -> None:
        if index == 1 and body is not None:
            raise OSError("evidence disk failed")
        saved(index, row, body)

    clients = (ScriptedClient(normal), ScriptedClient(normal))
    with pytest.raises(NativeBatchError, match="evidence disk failed") as caught:
        complete_cap_response(
            ROOT, CAP, clients, deadline=time.monotonic() + 1, preserve=preserve
        )
    assert caught.value.pending_payloads[1] == xml(LEFT)
    assert caught.value.ledger[1]["body_complete"]
    assert all(c.cancelled.is_set() for c in clients)


def test_deadline_cancels_both_and_keeps_original_partial_children() -> None:
    class Slow(ScriptedClient):
        def fetch(self, bounds: object, deadline: float) -> NativeResponse:
            self.calls.append(request_bounds(bounds))
            assert self.cancelled.wait(2)
            raise NativeHttpReadError(
                dict(
                    body_complete=False,
                    bytes=6,
                    sha256=hashlib.sha256(b"prefix").hexdigest(),
                    http_status=200,
                ),
                b"prefix",
            )

    clients = (Slow(normal), Slow(normal))
    saved = Saved()
    with pytest.raises(NativeBatchError) as caught:
        complete_cap_response(
            ROOT, CAP, clients, deadline=time.monotonic() + 0.1, preserve=saved
        )
    assert isinstance(caught.value.__cause__, TimeoutError)
    assert len([body for _, _, body in saved.rows if body == b"prefix"]) == 2
    assert all(c.cancelled.is_set() and len(c.calls) == 1 for c in clients)


@pytest.mark.parametrize("budget", [0, 256, True])
def test_illegal_request_budget_before_child_effects(budget: int) -> None:
    clients = (ScriptedClient(normal), ScriptedClient(normal))
    with pytest.raises(ValueError):
        complete_cap_response(
            ROOT,
            CAP,
            clients,
            deadline=time.monotonic() + 1,
            preserve=Saved(),
            max_requests=budget,
        )
    assert not any(c.calls for c in clients)


def test_budget_and_depth_exhaustion_preserve_original_and_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients = (ScriptedClient(normal), ScriptedClient(normal))
    with pytest.raises(NativeBatchError, match="request budget"):
        complete_cap_response(
            ROOT,
            CAP,
            clients,
            deadline=time.monotonic() + 1,
            preserve=Saved(),
            max_requests=1,
        )
    assert not any(c.calls for c in clients)
    monkeypatch.setattr(native_batch, "MAX_DEPTH", 0)
    fresh = (ScriptedClient(normal), ScriptedClient(normal))
    with pytest.raises(NativeBatchError, match="depth"):
        complete_cap_response(
            ROOT, CAP, fresh, deadline=time.monotonic() + 1, preserve=Saved()
        )
    assert not any(c.calls for c in fresh)


def test_distinct_exact_origin_clients_and_unexpired_deadline_required() -> None:
    client = ScriptedClient(normal)
    for clients in (
        (client, client),
        (client, NativeMapHttpClient("http://127.0.0.1:18081")),
    ):
        with pytest.raises(ValueError, match="distinct"):
            complete_cap_response(
                ROOT, CAP, clients, deadline=time.monotonic() + 1, preserve=Saved()
            )
    fresh = ScriptedClient(normal)
    for deadline in (-1, float("nan"), float("inf"), time.monotonic() + 301):
        with pytest.raises(ValueError, match="deadline"):
            complete_cap_response(
                ROOT, CAP, (client, fresh), deadline=deadline, preserve=Saved()
            )
    assert not client.calls and not fresh.calls
