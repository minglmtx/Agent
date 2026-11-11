"""Loopback-only HTTP provider. Never uses real credentials or remote models."""

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections.abc import Iterator
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.models.openrouter import OpenRouterTransport
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.model_request import ModelSendPlan, ResolvedModelRequest
from lab_generate_skill.runtime.lifecycle import OperationGuards
from model_sender_fixtures import SendFixture, send_fixture
from test_file_request_ledger import NoCancel

KEY = "unit-memory-credential"
REPLY = b'{"id":"unit-provider","choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"hello"}}],"usage":{"cost":0.000000002}}'
PARAMETERS = {
    "max_tokens": 128,
    "seed": 7,
    "temperature": 0,
    "provider": {"allow_fallbacks": False, "require_parameters": True},
}


def fixture(root: Path) -> SendFixture:
    f = send_fixture(root)
    ref = f.store.put(
        json.dumps(PARAMETERS, separators=(",", ":")).encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="model-parameters/1",
            visibility="private",
            producer="unit-fixture",
        ),
    )
    identity = f.plan.reservation.request.model_copy(
        update={"parameters_sha256": ref.sha256}
    )
    f.plan = ModelSendPlan.model_validate(
        f.plan.model_copy(
            update={
                "parameters_ref": ref,
                "reservation": f.plan.reservation.model_copy(
                    update={"request": identity}
                ),
            }
        )
    )
    return f


def resolved(f: SendFixture) -> ResolvedModelRequest:
    return ResolvedModelRequest(
        request=f.plan.reservation.request,
        input_bytes=f.store.read(f.plan.input_ref),
        parameters_bytes=f.store.read(f.plan.parameters_ref),
        limits=f.plan.limits,
    )


@dataclass
class Provider:
    status: int = 200
    body: bytes = REPLY
    truncated: bool = False
    wait: bool = False
    release: threading.Event = field(default_factory=threading.Event)
    received: threading.Event = field(default_factory=threading.Event)
    requests: list[tuple[str, bytes, str | None]] = field(default_factory=list)
    endpoint: str = ""


@contextmanager
def provider() -> Iterator[Provider]:
    config = Provider()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            data = self.rfile.read(int(self.headers["Content-Length"]))
            config.requests.append((self.path, data, self.headers.get("Authorization")))
            config.received.set()
            if config.wait:
                config.release.wait(5)
            try:
                self.send_response(config.status)
                self.send_header(
                    "Content-Length",
                    str(len(config.body) + (50 if config.truncated else 0)),
                )
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "0")
                self.send_header("Location", config.endpoint)
                self.end_headers()
                self.wfile.write(config.body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    config.endpoint = f"http://127.0.0.1:{server.server_port}/api/v1/chat/completions"
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.02), daemon=True
    )
    thread.start()
    try:
        yield config
    finally:
        config.release.set()
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive()


def transport(f: SendFixture, endpoint: str) -> OpenRouterTransport:
    return OpenRouterTransport(
        KEY,
        f.store,
        OperationGuards(SystemClock(), NoCancel()),
        endpoint=endpoint,
        test_loopback=True,
    )
