"""Two-client complete native MapData read under the original absolute deadline.

Only the actual known 50000-node-cap400 permits new child rectangles. Unknown
reads are never repeated; cancellation retains completed/partial siblings.
"""

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import heapq
import math
import re
import time
from typing import Any
from .native_bounds import Bounds, request_bounds, split_bounds, serialized_xml_bounds
from .native_http import NativeMapHttpClient, NativeResponse
from .native_xml import parse_native_xml
from .native_union import union_xml
from .native_batch_records import BatchRecords, NativeBatchError, PreserveChild

CAP_ERROR = re.compile(
    rb"^You requested too many nodes \(limit is 50000\)\. Either request a smaller area, or use planet\.osm\s*$"
)
MAX_REQUESTS = 255
MAX_DEPTH = 20


def complete_cap_response(
    original: object,
    original_response: NativeResponse,
    clients: tuple[NativeMapHttpClient, NativeMapHttpClient],
    *,
    deadline: float,
    preserve: PreserveChild,
    max_requests: int = MAX_REQUESTS,
) -> tuple[bytes, dict[str, Any]]:
    bounds = request_bounds(original)
    if (
        not isinstance(clients, tuple)
        or len(clients) != 2
        or clients[0] is clients[1]
        or any(not isinstance(c, NativeMapHttpClient) for c in clients)
        or clients[0].origin != clients[1].origin
    ):
        raise ValueError(
            "Two distinct exact-origin independent native HTTP clients required"
        )
    if type(max_requests) is not int or not 1 <= max_requests <= MAX_REQUESTS:
        raise ValueError("Original bounded native request budget required")
    if (
        type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or not 0 < deadline - time.monotonic() <= 300
    ):
        raise ValueError("Unexpired original absolute native deadline required")
    if (
        not isinstance(original_response, NativeResponse)
        or type(original_response.status) is not int
        or original_response.status != 400
        or not isinstance(original_response.body, bytes)
        or CAP_ERROR.fullmatch(original_response.body) is None
    ):
        raise ValueError("Actual unchanged native 50000-node-cap400 required")
    records = BatchRecords(preserve)
    leaves: list[tuple[Bounds, bytes]] = []
    pending: list[tuple[tuple[int, ...], Bounds]] = []
    running: dict[Future[NativeResponse], tuple[int, dict[str, Any], float]] = {}
    available = [0, 1]
    executor = ThreadPoolExecutor(
        max_workers=2, thread_name_prefix="native-map-independent-read"
    )
    failed = False

    def consume(row: dict[str, Any], response: NativeResponse, began: float) -> None:
        records.response(row, response, began)
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Original native absolute deadline exhausted after response"
            )
        if response.status == 400 and CAP_ERROR.fullmatch(response.body):
            row["native_node_cap"] = 50000
            records.save(row, response.body)
            if row["depth"] >= MAX_DEPTH:
                raise ValueError("Original native subdivision depth exhausted")
            for number, child in enumerate(split_bounds(row["bounds"])):
                heapq.heappush(pending, (tuple(row["split_path"]) + (number,), child))
            return
        if response.status != 200 or response.content_type.split(";", 1)[
            0
        ].strip().lower() not in ("application/xml", "text/xml"):
            raise ValueError(
                "Native child is not HTTP200 XML; original non-cap error retained"
            )
        parsed = parse_native_xml(response.body)
        if parsed.bounds != serialized_xml_bounds(row["bounds"]):
            raise ValueError("Native child XML bounds differ from request")
        leaves.append((request_bounds(row["bounds"]), response.body))

    def completed(
        future: Future[NativeResponse],
        row: dict[str, Any],
        began: float,
        *,
        after_failure: bool,
    ) -> None:
        try:
            response = future.result()
        except BaseException as error:
            records.failed(row, error, began)
            raise
        if after_failure:
            records.response(row, response, began, after_failure=True)
        else:
            consume(row, response, began)

    try:
        parent = records.start((), bounds)
        consume(parent, original_response, time.monotonic())
        while pending or running:
            if time.monotonic() >= deadline:
                raise TimeoutError("Original native absolute deadline exhausted")
            while pending and available:
                if len(records.rows) >= max_requests:
                    raise ValueError("Original native request budget exhausted")
                path, cell = heapq.heappop(pending)
                row = records.start(path, cell)
                slot = available.pop(0)
                began = time.monotonic()
                future = executor.submit(clients[slot].fetch, cell, deadline)
                running[future] = (slot, row, began)
            done, _ = wait(
                running,
                timeout=max(0, deadline - time.monotonic()),
                return_when=FIRST_COMPLETED,
            )
            if not done:
                raise TimeoutError("Original native absolute deadline exhausted")
            for future in sorted(
                done, key=lambda f: tuple(running[f][1]["split_path"])
            ):
                slot, row, began = running.pop(future)
                available.append(slot)
                completed(future, row, began, after_failure=False)
        if time.monotonic() >= deadline:
            raise TimeoutError("Original native deadline exhausted before union")
        payload, summary = union_xml(bounds, leaves)
        if time.monotonic() >= deadline:
            raise TimeoutError("Original native deadline exhausted during union")
        summary.update(
            requests=sorted(records.rows, key=lambda row: tuple(row["split_path"])),
            native_parent_http_status=400,
            no_private_oracle_used_to_construct_union=True,
            each_child_uses_original_native_endpoint=True,
            transport_version="map-native-two-independent-http-clients-v1",
            maximum_independent_http_clients=2,
            playwright_thread_shared=False,
            original_absolute_deadline_renewed=False,
            complete_full_union_required=True,
        )
        return payload, summary
    except BaseException as error:
        failed = True
        for client in clients:
            try:
                client.cancel()
            except BaseException as cleanup:
                records.cleanup_errors.append(type(cleanup).__name__)
        # One independent bounded cleanup interval, never a renewed read budget.
        close_deadline = time.monotonic() + 2
        for future, (_, row, began) in running.items():
            try:
                future.result(timeout=max(0, close_deadline - time.monotonic()))
            except BaseException:
                pass  # Read/timeout diagnostics are saved below, not treated as success.
            try:
                if future.done():
                    completed(future, row, began, after_failure=True)
                else:
                    row.update(
                        status="native_client_cleanup_unknown", body_complete=False
                    )
                    records.save(row)
            except BaseException as cleanup:
                records.cleanup_errors.append(type(cleanup).__name__)
        raise NativeBatchError(str(error), records) from error
    finally:
        executor.shutdown(wait=not failed, cancel_futures=failed)
