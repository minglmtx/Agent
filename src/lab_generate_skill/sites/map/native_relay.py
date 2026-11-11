"""Owned loopback transport for original MapData XHRs, off Playwright's thread.

Registration records intent and returns a private once-only URL. Only an actual
GET to that URL runs NativeExchange. No page handle, Actor action, DB oracle or
automatic replay is available here. The browser collector must bind actual XHR
provenance and stop this writer before publishing its complete file manifest.
"""

from dataclasses import dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
import threading
import time
import traceback
from typing import Any
from uuid import uuid4
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_private_artifact import MapArtifactSink
from .native_http import NativeMapHttpClient, NativeResponse
from .native_exchange import NativeExchange


@dataclass
class RelayRequest:
    exchange: NativeExchange
    target: str
    started: bool = False
    finished: bool = False
    thread: threading.Thread | None = None
    connection: socket.socket | None = None
    delivered: int = 0
    delivery_complete: bool = False
    closing_record_attempted: bool = False
    errors: list[BaseException] = field(default_factory=list)


class NativeMapRelay:
    def __init__(
        self,
        origin: str,
        sink: MapArtifactSink,
        evidence_control: OperationControl,
        *,
        max_requests: int,
    ) -> None:
        self.origin = NativeMapHttpClient(origin).origin
        if (
            type(max_requests) is not int
            or not 1 <= max_requests <= 256
            or not callable(getattr(sink, "retain", None))
        ):
            raise ValueError(
                "Explicit bounded request capacity and private sink required"
            )
        self.sink, self.evidence_control = sink, evidence_control
        self.max_requests = max_requests
        self.owner = os.getpid()
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.state = "new"
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.requests: dict[str, RelayRequest] = {}
        self.identities: set[str] = set()
        self.registration_error: BaseException | None = None
        self.cleanup_errors: list[BaseException] = []
        self.physical_closed = False
        self.handler_threads: list[threading.Thread] = []
        self.handler_sockets: dict[threading.Thread, socket.socket] = {}

    def _owner(self) -> None:
        if os.getpid() != self.owner:
            raise OwnershipConflict(
                "Native relay belongs to its original browser process"
            )

    def _record(
        self, name: str, value: dict[str, Any], *, control: OperationControl
    ) -> None:
        data = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        expected = ReleaseFile(
            path=name,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            executable=False,
        )
        if self.sink.retain(name, data, control) != expected:
            raise EvidenceIntegrityError("Native relay record pin differs")

    def start(self, control: OperationControl) -> None:
        self._owner()
        with self.lock:
            if self.state != "new":
                raise InvalidTransition("Original native relay starts only once")
            control.checkpoint()
            self.evidence_control.checkpoint()
            self.state = "starting"
            outer = self

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, format: str, *args: object) -> None:
                    pass

                def do_GET(self) -> None:
                    outer._get(self)

            class OwnedServer(ThreadingHTTPServer):
                def process_request(
                    self,
                    request: socket.socket | tuple[bytes, socket.socket],
                    client_address: Any,
                ) -> None:
                    if not isinstance(request, socket.socket):
                        raise TypeError("Original native relay requires a TCP socket")
                    with outer.lock:
                        if (
                            outer.stop.is_set()
                            or len(outer.handler_threads) >= 4 * outer.max_requests + 16
                        ):
                            self.shutdown_request(request)
                            return
                        request.settimeout(10)
                        thread = threading.Thread(
                            target=self.process_request_thread,
                            args=(request, client_address),
                            name="map-native-relay-request",
                            daemon=True,
                        )
                        outer.handler_threads.append(thread)
                        outer.handler_sockets[thread] = request
                        thread.start()

                def process_request_thread(
                    self,
                    request: socket.socket | tuple[bytes, socket.socket],
                    client_address: Any,
                ) -> None:
                    if not isinstance(request, socket.socket):
                        raise TypeError("Original native relay requires a TCP socket")
                    try:
                        super().process_request_thread(request, client_address)
                    finally:
                        with outer.lock:
                            outer.handler_sockets.pop(threading.current_thread(), None)

            self.server = OwnedServer(("127.0.0.1", 0), Handler)
            self.server.daemon_threads = True
            self.server.block_on_close = False
            self.thread = threading.Thread(
                target=self.server.serve_forever,
                kwargs={"poll_interval": 0.02},
                name="map-native-relay",
                daemon=True,
            )
            self.state = "active"
            self.thread.start()
            control.checkpoint()

    def register(
        self,
        request_id: str,
        bounds: object,
        deadline: float,
        control: OperationControl,
    ) -> str:
        self._owner()
        exchange = NativeExchange(
            request_id, self.origin, bounds, deadline, self.sink, self.evidence_control
        )
        with self.lock:
            if self.state != "active" or self.stop.is_set():
                raise InvalidTransition("Native relay is not accepting requests")
            if request_id in self.identities:
                raise InvalidTransition(
                    "Original browser request cannot be registered twice"
                )
            if len(self.identities) >= self.max_requests:
                raise ValueError("Explicit native browser request capacity exhausted")
            control.checkpoint()
            target = "/native-map-pending/" + uuid4().hex + ".osm"
            self.identities.add(request_id)
            try:
                self._record(
                    request_id + "-registration.json",
                    dict(
                        schema_version="map-native-relay-registration/1",
                        request_id=request_id,
                        original_origin=self.origin,
                        bounds=list(exchange.bounds),
                        original_absolute_monotonic_deadline=deadline,
                        dispatch_on_first_private_get_only=True,
                        actual_browser_provenance_verified=False,
                    ),
                    control=self.evidence_control,
                )
                self.requests[target] = RelayRequest(exchange, target)
                assert self.server is not None
                control.checkpoint()
                return f"http://127.0.0.1:{self.server.server_port}{target}"
            except BaseException as error:
                self.registration_error = error
                self.state = "failed"
                raise

    def _get(self, handler: BaseHTTPRequestHandler) -> None:
        if handler.headers.get("Origin") not in (None, self.origin):
            handler.send_error(403)
            return
        with self.lock:
            job = self.requests.get(handler.path)
            if job is None:
                handler.send_error(404)
                return
            if self.state != "active" or self.stop.is_set() or job.started:
                handler.send_error(410)
                return
            job.started = True
            job.thread = threading.current_thread()
            job.connection = handler.connection
        headers_sent = False
        try:
            result = job.exchange.run()
            response = result.response
            if len(response.content_type) > 1024 or any(
                ord(c) < 32 or ord(c) == 127 for c in response.content_type
            ):
                raise ValueError(
                    "Original native content type cannot be relayed as an HTTP header"
                )
            self._record(
                job.exchange.request_id + "-delivery-start.json",
                dict(
                    original_http_status=result.original_http_status,
                    adapted=result.adapted,
                    delivered_http_status=response.status,
                    payload=result.payload.model_dump(mode="json"),
                    batch=result.batch,
                    native_original_http200_claim=not result.adapted
                    and result.original_http_status == 200,
                ),
                control=self.evidence_control,
            )
            if self.stop.is_set():
                raise TimeoutError("Original relay closed before delivery")
            # Separate bounded original delivery lifetime, never a renewed native
            # fetch deadline. Complete body bytes are already durably retained.
            deadline = time.monotonic() + 90
            handler.connection.settimeout(min(10, self.evidence_control.checkpoint()))
            handler.send_response(response.status)
            handler.send_header("Content-Type", response.content_type)
            handler.send_header("Content-Length", str(len(response.body)))
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Access-Control-Allow-Origin", self.origin)
            handler.end_headers()
            headers_sent = True
            self._deliver(handler, job, response, deadline)
        except BaseException as error:
            job.errors.append(error)
            if not headers_sent and not self.stop.is_set():
                try:
                    handler.send_error(502, "Original native transport incomplete")
                except BaseException as delivery_error:
                    job.errors.append(delivery_error)
        finally:
            try:
                self._record(
                    job.exchange.request_id + "-delivery-end.json",
                    dict(
                        delivered_bytes=job.delivered,
                        delivery_complete=job.delivery_complete,
                        exchange_state=job.exchange.state,
                        errors=[
                            "".join(traceback.format_exception(e)) for e in job.errors
                        ],
                    ),
                    control=self.evidence_control,
                )
            except BaseException as error:
                job.errors.append(error)
            with self.lock:
                job.finished = True
                job.connection = None

    def _deliver(
        self,
        handler: BaseHTTPRequestHandler,
        job: RelayRequest,
        response: NativeResponse,
        deadline: float,
    ) -> None:
        for offset in range(0, len(response.body), 1024 * 1024):
            remaining = min(
                deadline - time.monotonic(), self.evidence_control.checkpoint()
            )
            if self.stop.is_set() or remaining <= 0:
                raise TimeoutError("Original native delivery expired or closed")
            handler.connection.settimeout(min(10, remaining))
            block = response.body[offset : offset + 1024 * 1024]
            handler.wfile.write(block)
            job.delivered += len(block)
        job.delivery_complete = True

    def close(self, control: OperationControl) -> None:
        self._owner()
        if self.state == "closed":
            return
        control.checkpoint()
        with self.lock:
            self.stop.set()
            self.state = "closing"
            jobs = list(self.requests.values())
        errors: list[BaseException] = []
        for job in jobs:
            try:
                job.exchange.cancel()
            except BaseException as error:
                errors.append(error)
            if job.connection is not None:
                try:
                    job.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # Already closed original connection; no replacement.
        if self.server is not None:
            try:
                if self.thread is not None and self.thread.is_alive():
                    self.server.shutdown()
                self.server.server_close()
            except BaseException as error:
                errors.append(error)
        # Includes accepted connections whose request headers never completed,
        # not just those already associated with a native job.
        with self.lock:
            sockets = list(self.handler_sockets.values())
            handlers = list(self.handler_threads)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for thread in [self.thread] + handlers:
            if thread is not None:
                try:
                    thread.join(timeout=control.checkpoint())
                    if thread.is_alive():
                        raise RuntimeError("Original native relay thread remains live")
                except BaseException as error:
                    errors.append(error)
        self.physical_closed = all(
            t is None or not t.is_alive() for t in [self.thread] + handlers
        ) and (self.server is None or self.server.socket.fileno() == -1)
        for job in jobs:
            if not job.started and not job.closing_record_attempted:
                job.closing_record_attempted = True
                try:
                    self._record(
                        job.exchange.request_id + "-never-requested.json",
                        dict(
                            status="unknown",
                            reason="browser_never_requested_registered_native_job",
                            native_dispatches=0,
                        ),
                        control=control,
                    )
                except BaseException as error:
                    errors.append(error)
        self.cleanup_errors.extend(errors)
        self.state = "quarantined" if self.cleanup_errors else "closed"
        if self.cleanup_errors:
            raise BaseExceptionGroup(
                "Original native relay cleanup failures", self.cleanup_errors
            )
