"""One anonymous exact-origin native GET; no redirects, proxy, auth or retry.

Selected original map_native_bbox_http_client behavior, with owned sockets for
deadline/cancellation and complete partial-byte diagnostics. The batch caller
decides whether a known original node-cap400 permits distinct child requests.
"""

from dataclasses import dataclass
import errno
import hashlib
import http.client
import ipaddress
import math
import select
import socket
import threading
import time
from typing import Any
from urllib.parse import urlencode, urlsplit
from .native_bounds import request_bounds

MAX_NATIVE_CHILD_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class NativeResponse:
    status: int
    content_type: str
    body: bytes


class NativeHttpReadError(IOError):
    def __init__(self, record: dict[str, Any], partial: bytes) -> None:
        super().__init__("Actual independent native HTTP read did not complete")
        self.record, self.partial = dict(record), partial


class NativeMapHttpClient:
    def __init__(self, origin: str) -> None:
        if not isinstance(origin, str):
            raise ValueError("Exact anonymous native loopback origin required")
        parsed = urlsplit(origin)
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
            port = parsed.port
        except ValueError:
            raise ValueError(
                "Exact anonymous native loopback origin required"
            ) from None
        if (
            parsed.scheme != "http"
            or not address.is_loopback
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or port is None
            or not 1 <= port <= 65535
            or any(c.isspace() or ord(c) < 32 or c == "\\" for c in origin)
        ):
            raise ValueError("Exact anonymous native loopback origin required")
        self.origin = origin.rstrip("/")
        self.host, self.port = str(address), port
        self.address_version = address.version
        self.lock = threading.Lock()
        self.connection: http.client.HTTPConnection | None = None
        self.socket: socket.socket | None = None
        self.cancelled = threading.Event()

    def cancel(self) -> None:
        self.cancelled.set()
        with self.lock:
            connection, sock = self.connection, self.socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # Already closed/not connected; fetch retains its actual error.
        if connection is not None:
            connection.close()

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or self.cancelled.is_set():
            raise TimeoutError("Original absolute native deadline/cancellation reached")
        return remaining

    def fetch(self, bounds: object, deadline: float) -> NativeResponse:
        path = "/api/0.6/map?" + urlencode({"bbox": ",".join(request_bounds(bounds))})
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("Finite original absolute deadline required")
        remaining = self._remaining(deadline)
        if remaining > 300:
            raise ValueError(
                "Original native request deadline cannot exceed 300 seconds"
            )
        connection = http.client.HTTPConnection(self.host, self.port, timeout=remaining)
        with self.lock:
            if self.connection is not None:
                raise ValueError("Independent client cannot have concurrent requests")
            self.connection = connection
        chunks: list[bytes] = []
        record: dict[str, Any] = dict(
            http_status=None,
            content_type=None,
            body_complete=False,
            request_path=path,
            request_started=False,
            cleanup_errors=[],
        )
        failure: BaseException | None = None
        response: http.client.HTTPResponse | None = None
        result: NativeResponse | None = None
        try:
            sock = socket.socket(
                socket.AF_INET6 if self.address_version == 6 else socket.AF_INET,
                socket.SOCK_STREAM,
            )
            with self.lock:
                self.socket = sock
            sock.setblocking(False)
            self._remaining(deadline)
            error = sock.connect_ex((self.host, self.port))
            if error not in (
                0,
                errno.EISCONN,
                errno.EINPROGRESS,
                errno.EWOULDBLOCK,
                errno.EALREADY,
            ):
                raise OSError(error, "Native loopback connect failed")
            while error not in (0, errno.EISCONN):
                remaining = self._remaining(deadline)
                _, ready, failed = select.select(
                    [], [sock], [sock], min(0.05, remaining)
                )
                if ready or failed:
                    error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    if error:
                        raise OSError(error, "Native loopback connect failed")
            sock.setblocking(True)
            sock.settimeout(self._remaining(deadline))
            connection.sock = sock
            record["request_started"] = True
            connection.request("GET", path, headers={"Accept": "application/xml"})
            sock.settimeout(self._remaining(deadline))
            response = connection.getresponse()
            content_type = response.getheader("Content-Type", "")
            record.update(http_status=response.status, content_type=content_type)
            declared = response.getheader("Content-Length")
            if declared is not None and (
                not declared.isdecimal() or int(declared) > MAX_NATIVE_CHILD_BYTES
            ):
                raise ValueError(
                    "Native response exceeds unchanged 64MiB inspection budget"
                )
            total = 0
            while True:
                sock.settimeout(self._remaining(deadline))
                block = response.read1(1024 * 1024)
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                if total > MAX_NATIVE_CHILD_BYTES:
                    raise ValueError(
                        "Native response exceeds unchanged 64MiB inspection budget"
                    )
                if response.isclosed():
                    break
            body = b"".join(chunks)
            if declared is not None and len(body) != int(declared):
                raise http.client.IncompleteRead(body)
            self._remaining(deadline)
            record["body_complete"] = True
            result = NativeResponse(response.status, content_type, body)
        except BaseException as error:
            failure = error
        finally:
            with self.lock:
                owned_socket = self.socket
            for item in (response, connection, owned_socket):
                if item is not None:
                    try:
                        item.close()
                    except BaseException as error:
                        record["cleanup_errors"].append(type(error).__name__)
                        if failure is None:
                            failure = error
            with self.lock:
                self.connection = None
                self.socket = None
        if failure is not None:
            partial = b"".join(chunks)
            record.update(
                bytes=len(partial),
                sha256=hashlib.sha256(partial).hexdigest(),
                failure_type=type(failure).__name__,
            )
            raise NativeHttpReadError(record, partial) from failure
        assert result is not None
        return result
