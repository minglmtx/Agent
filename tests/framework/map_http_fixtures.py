"""Controlled HTTP only: never a real Map DB or inferred native response."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from typing import Iterator
from urllib.parse import parse_qs, urlsplit
from map_xml_fixtures import xml


@dataclass
class HttpFixture:
    mode: str
    origin: str = ""
    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    waiting: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)


@contextmanager
def http_fixture(mode: str = "normal") -> Iterator[HttpFixture]:
    fixture = HttpFixture(mode)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            fixture.calls.append(
                (self.path, {k.lower(): v for k, v in self.headers.items()})
            )
            if mode == "headers":
                fixture.waiting.set()
                fixture.release.wait(2)
            status = 302 if mode == "redirect" else 400 if mode == "cap" else 200
            body = b"cap error preserved" if mode == "cap" else xml()
            if mode == "batch":
                bounds = tuple(
                    parse_qs(urlsplit(self.path).query)["bbox"][0].split(",")
                )
                if bounds == ("0", "0", "0.5", "0.5"):
                    status = 400
                    body = b"You requested too many nodes (limit is 50000). Either request a smaller area, or use planet.osm\n"
                else:
                    body = xml(bounds)
            if mode in ("partial", "body"):
                body = b"prefix"
            self.send_response(status)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Location", "/should-not-follow")
            length = "100" if mode in ("partial", "body") else str(len(body))
            if mode == "oversized":
                length = str(64 * 1024 * 1024 + 1)
            if mode == "bad-length":
                length = "unknown"
            self.send_header("Content-Length", length)
            self.end_headers()
            try:
                self.wfile.write(body)
                self.wfile.flush()
                fixture.waiting.set()
                if mode == "body":
                    fixture.release.wait(2)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    fixture.origin = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield fixture
    finally:
        fixture.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()
