"""One original browser MapData request, executed off the Playwright thread.

This joins the already verified native HTTP/batch/file components. A private
relay may deliver the result, but only after complete bytes are retained. No
browser object, database oracle, retry, dispatch admission or server lives here.
"""

from dataclasses import dataclass
import hashlib
import math
import threading
import time
from typing import Any
from lab_generate_skill.domain.errors import InvalidTransition, EvidenceIntegrityError
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.map_private_artifact import MapArtifactSink
from lab_generate_skill.ports.lifecycle import OperationControl
from .native_bounds import request_bounds
from .native_http import NativeMapHttpClient, NativeResponse
from .native_batch import CAP_ERROR, complete_cap_response
from .native_batch_records import BatchRecords
from .native_retention import NativeBatchRetention


@dataclass(frozen=True)
class NativeExchangeResult:
    response: NativeResponse
    payload: ReleaseFile
    original_http_status: int
    adapted: bool
    batch: dict[str, Any] | None


class NativeExchange:
    def __init__(
        self,
        request_id: str,
        origin: str,
        bounds: object,
        deadline: float,
        sink: MapArtifactSink,
        evidence_control: OperationControl,
    ) -> None:
        # Both retention namespaces and the HTTP origin are validated before
        # effects. This caps request_id at26 characters, allowing each suffix.
        if not isinstance(request_id, str):
            raise ValueError("Explicit bounded native request identity required")
        self.original_retention = NativeBatchRetention(
            request_id + "-first", sink, evidence_control
        )
        self.child_retention = NativeBatchRetention(
            request_id + "-batch", sink, evidence_control
        )
        self.bounds = request_bounds(bounds)
        if (
            type(deadline) not in (float, int)
            or not math.isfinite(deadline)
            or not 0 < deadline - time.monotonic() <= 300
        ):
            raise ValueError("Original finite unexpired native deadline required")
        self.clients = tuple(NativeMapHttpClient(origin) for _ in range(3))
        self.request_id, self.deadline = request_id, deadline
        self.sink, self.evidence_control = sink, evidence_control
        self.records = BatchRecords(self.original_retention)
        self.lock = threading.Lock()
        self.cancelled = threading.Event()
        self.state = "new"
        self.original: NativeResponse | None = None
        self.pending_response: NativeResponse | None = None
        self.result: NativeExchangeResult | None = None
        self.error: BaseException | None = None
        self.cleanup_errors: list[BaseException] = []

    def cancel(self) -> None:
        self.cancelled.set()
        for client in self.clients:
            client.cancel()

    def run(self) -> NativeExchangeResult:
        with self.lock:
            if self.state != "new":
                raise InvalidTransition("Original native exchange cannot run twice")
            self.state = "running"
        try:
            if self.cancelled.is_set() or time.monotonic() >= self.deadline:
                raise TimeoutError("Original native exchange cancelled or expired")
            row = self.records.start((), self.bounds)
            began = time.monotonic()
            try:
                original = self.clients[0].fetch(self.bounds, self.deadline)
            except BaseException as error:
                try:
                    self.records.failed(row, error, began)
                except BaseException as retention_error:
                    raise BaseExceptionGroup(
                        "Original read and failure retention", [error, retention_error]
                    )
                raise
            self.original = self.pending_response = original
            self.records.response(row, original, began)
            response, adapted = original, False
            batch: dict[str, Any] | None = None
            if original.status == 400 and CAP_ERROR.fullmatch(original.body):
                payload, batch = complete_cap_response(
                    self.bounds,
                    original,
                    (self.clients[1], self.clients[2]),
                    deadline=self.deadline,
                    preserve=self.child_retention,
                )
                response = NativeResponse(
                    200, "application/xml; charset=utf-8", payload
                )
                adapted = True
            self.pending_response = response
            # Original non-cap errors/redirects remain the original response.
            # The consumer must not interpret complete bytes as task success.
            expected = ReleaseFile(
                path=self.request_id + "-response.bin",
                sha256=hashlib.sha256(response.body).hexdigest(),
                size_bytes=len(response.body),
                executable=False,
            )
            retained = self.sink.retain(
                expected.path, response.body, self.evidence_control
            )
            if retained != expected:
                raise EvidenceIntegrityError(
                    "Complete native exchange response pin differs"
                )
            if self.cancelled.is_set() or time.monotonic() >= self.deadline:
                raise TimeoutError("Original exchange expired after bytes retained")
            self.result = NativeExchangeResult(
                response, retained, original.status, adapted, batch
            )
        except BaseException as error:
            self.error = error
        finally:
            for client in self.clients:
                try:
                    client.cancel()
                except BaseException as error:
                    self.cleanup_errors.append(error)
        errors = ([self.error] if self.error is not None else []) + self.cleanup_errors
        if errors:
            self.state = "failed"
            if len(errors) == 1:
                raise errors[0]
            raise BaseExceptionGroup(
                "Original native exchange and cleanup failures", errors
            )
        self.state = "complete"
        self.pending_response = None
        assert self.result is not None
        return self.result
