"""Preserve each native request transition before batching can advance."""

from copy import deepcopy
import hashlib
import time
from typing import Any, Callable, TypeAlias
from .native_http import NativeResponse, NativeHttpReadError

PreserveChild: TypeAlias = Callable[[int, dict[str, Any], bytes | None], None]


class NativeBatchError(ValueError):
    def __init__(self, message: str, records: "BatchRecords") -> None:
        super().__init__(message)
        self.ledger = deepcopy(records.rows)
        self.pending_payloads = dict(records.pending_payloads)
        self.cleanup_errors = tuple(records.cleanup_errors)


class BatchRecords:
    def __init__(self, preserve: PreserveChild) -> None:
        if not callable(preserve):
            raise ValueError("Native response preservation is required")
        self.preserve = preserve
        self.rows: list[dict[str, Any]] = []
        self.pending_payloads: dict[int, bytes] = {}
        self.cleanup_errors: list[str] = []

    def save(self, row: dict[str, Any], payload: bytes | None = None) -> None:
        index = row["request_index"]
        if payload is not None:
            self.pending_payloads[index] = payload
        self.preserve(index, deepcopy(row), payload)
        self.pending_payloads.pop(index, None)

    def start(self, path: tuple[int, ...], bounds: tuple[str, ...]) -> dict[str, Any]:
        row = dict(
            request_index=len(self.rows),
            split_path=list(path),
            parent_split_path=list(path[:-1]) if path else None,
            bounds=list(bounds),
            http_status=None,
            depth=len(path),
            status="started",
            seconds=None,
            body_complete=False,
        )
        self.rows.append(row)
        self.save(row)
        return row

    def response(
        self,
        row: dict[str, Any],
        response: NativeResponse,
        began: float,
        *,
        after_failure: bool = False,
    ) -> None:
        if (
            not isinstance(response, NativeResponse)
            or type(response.status) is not int
            or not isinstance(response.body, bytes)
            or not isinstance(response.content_type, str)
        ):
            row.update(
                status="invalid_response_schema", seconds=time.monotonic() - began
            )
            self.save(row)
            raise ValueError("Actual native child response schema unavailable")
        row.update(
            status=(
                "response_retained_after_batch_failure"
                if after_failure
                else "response_received"
            ),
            http_status=response.status,
            content_type=response.content_type,
            bytes=len(response.body),
            sha256=hashlib.sha256(response.body).hexdigest(),
            seconds=time.monotonic() - began,
            body_complete=True,
        )
        self.save(row, response.body)

    def failed(self, row: dict[str, Any], error: BaseException, began: float) -> None:
        row.update(
            status="transport_failed",
            failure_type=type(error).__name__,
            seconds=time.monotonic() - began,
        )
        payload = None
        if isinstance(error, NativeHttpReadError):
            row.update(error.record)
            payload = error.partial
        self.save(row, payload)
