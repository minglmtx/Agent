"""Real bounded loopback sockets; no retries or browser/DB/Actor required."""

import hashlib
import threading
import time
from urllib.parse import parse_qs, urlsplit
import pytest
from lab_generate_skill.sites.map.native_http import (
    NativeMapHttpClient,
    NativeHttpReadError,
)
from lab_generate_skill.sites.map.native_xml import parse_native_xml
from map_xml_fixtures import ROOT, xml
from map_http_fixtures import http_fixture


def test_anonymous_exact_request_complete_body_and_independent_repeat() -> None:
    with http_fixture() as server:
        client = NativeMapHttpClient(server.origin)
        for _ in range(2):
            response = client.fetch(ROOT, time.monotonic() + 2)
            assert response.status == 200 and response.body == xml()
            assert parse_native_xml(response.body).bounds == ROOT
            assert client.connection is None and client.socket is None
        assert len(server.calls) == 2
        for path, headers in server.calls:
            assert urlsplit(path).path == "/api/0.6/map"
            assert parse_qs(urlsplit(path).query) == {"bbox": ["0,0,0.5,0.5"]}
            assert headers["accept"] == "application/xml"
            assert not any(
                k in headers for k in ("cookie", "authorization", "proxy-authorization")
            )


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "",
        "https://127.0.0.1:1234",
        "http://example.com:1234",
        "http://192.0.2.1:1234",
        "http://127.0.0.1",
        "http://user@127.0.0.1:1234",
        "http://127.0.0.1:1234/path",
        "http://127.0.0.1:1234?x=1",
        "http://127.0.0.1:1234#x",
        "http://127.0.0.1:99999",
        "http://127.0.0.1:1234\n",
    ],
)
def test_foreign_credentialed_malformed_origin_refused(origin: str) -> None:
    with pytest.raises(ValueError):
        NativeMapHttpClient(origin)


@pytest.mark.parametrize("mode,status", [("redirect", 302), ("cap", 400)])
def test_original_non200_preserved_without_following_or_retry(
    mode: str, status: int
) -> None:
    with http_fixture(mode) as server:
        response = NativeMapHttpClient(server.origin).fetch(ROOT, time.monotonic() + 2)
        assert response.status == status and len(server.calls) == 1
        assert response.body == (b"cap error preserved" if mode == "cap" else xml())


@pytest.mark.parametrize(
    "mode", ["partial", "oversized", "bad-length", "headers", "body"]
)
def test_partial_failed_or_deadline_read_saved_and_not_retried(mode: str) -> None:
    with http_fixture(mode) as server:
        client = NativeMapHttpClient(server.origin)
        began = time.monotonic()
        with pytest.raises(NativeHttpReadError) as caught:
            client.fetch(ROOT, began + 0.3)
        error = caught.value
        assert time.monotonic() - began < 1.5
        assert len(server.calls) == 1 and not error.record["body_complete"]
        assert error.record["bytes"] == len(error.partial)
        assert error.record["sha256"] == hashlib.sha256(error.partial).hexdigest()
        assert error.record["request_started"]
        assert error.record["cleanup_errors"] == []
        assert client.socket is None and client.connection is None
        if mode in ("partial", "body"):
            assert error.partial == b"prefix"


def test_cancellation_interrupts_original_read_and_blocks_new_requests() -> None:
    with http_fixture("body") as server:
        client = NativeMapHttpClient(server.origin)
        errors: list[BaseException] = []

        def read() -> None:
            try:
                client.fetch(ROOT, time.monotonic() + 5)
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=read)
        thread.start()
        assert server.waiting.wait(2)
        with pytest.raises(ValueError, match="concurrent"):
            client.fetch(ROOT, time.monotonic() + 1)
        client.cancel()
        client.cancel()
        thread.join(timeout=2)
        assert not thread.is_alive() and len(errors) == 1
        assert isinstance(errors[0], NativeHttpReadError)
        assert not errors[0].record["body_complete"]
        with pytest.raises(TimeoutError):
            client.fetch(ROOT, time.monotonic() + 1)
        assert (
            len(server.calls) == 1
            and client.socket is None
            and client.connection is None
        )


@pytest.mark.parametrize("deadline", [float("nan"), float("inf"), True, -1.0])
def test_bad_or_expired_deadline_refused_before_request(deadline: float) -> None:
    with http_fixture() as server:
        with pytest.raises((ValueError, TimeoutError)):
            NativeMapHttpClient(server.origin).fetch(ROOT, deadline)
        assert not server.calls


def test_oversized_budget_bad_bbox_and_precancel_no_request() -> None:
    with http_fixture() as server:
        client = NativeMapHttpClient(server.origin)
        with pytest.raises(ValueError):
            client.fetch(ROOT, time.monotonic() + 301)
        with pytest.raises(ValueError):
            client.fetch([0, 0, 1, 1], time.monotonic() + 1)
        client.cancel()
        with pytest.raises(TimeoutError):
            client.fetch(ROOT, time.monotonic() + 1)
        assert not server.calls
