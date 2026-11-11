"""Recompute the complete recorded cap transport, with no HTTP or database calls."""

import json
import hashlib
from typing import Any
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .terminal_files import TerminalFiles
from .state_rules import object_json
from .native_bounds import Bounds, request_bounds, split_bounds
from .native_batch import CAP_ERROR
from .native_union import union_xml


def transport_events(
    files: TerminalFiles, prefix: str, control: OperationControl
) -> tuple[list[dict[str, Any]], dict[int, bytes]]:
    names = sorted(
        n
        for n in files.members
        if n.startswith(prefix + "-event-") and n.endswith(".json")
    )
    if not names or len(names) > 2048:
        raise EvidenceIntegrityError("Complete original native event sequence required")
    rows: dict[int, dict[str, Any]] = {}
    bodies: dict[int, bytes] = {}
    for sequence, name in enumerate(names):
        if name != f"{prefix}-event-{sequence:04d}.json":
            raise EvidenceIntegrityError("Native event sequence has a gap")
        event = object_json(files.read(name, control))
        index = event.get("request_index")
        if (
            set(event)
            != {
                "schema_version",
                "batch_id",
                "event_index",
                "request_index",
                "source_record",
                "body",
            }
            or event["schema_version"] != "map-native-transport-event/1"
            or event["batch_id"] != prefix
            or type(event["event_index"]) is not int
            or event["event_index"] != sequence
            or type(index) is not int
            or not 0 <= index < 255
        ):
            raise EvidenceIntegrityError("Native event changed original identity")
        row = event["source_record"]
        if (
            type(row) is not dict
            or type(row.get("request_index")) is not int
            or row["request_index"] != index
        ):
            raise EvidenceIntegrityError("Native event changed original request row")
        status = row.get("status")
        if index not in rows:
            if (
                index != len(rows)
                or status != "started"
                or row.get("body_complete") is not False
                or event["body"] is not None
            ):
                raise EvidenceIntegrityError("Native request lost its original start")
        elif status != "response_received" or row.get("body_complete") is not True:
            raise EvidenceIntegrityError(
                "Native request has incomplete/failed response evidence"
            )
        if index in rows:
            previous = rows[index]
            keys = (
                previous.keys()
                if previous.get("status") == "response_received"
                else (
                    "request_index",
                    "bounds",
                    "split_path",
                    "parent_split_path",
                    "depth",
                )
            )
            if any(row.get(k) != previous[k] for k in keys):
                raise EvidenceIntegrityError(
                    "Native event rewrote an original request/response"
                )
        if event["body"] is not None:
            entry = ReleaseFile.model_validate_json(json.dumps(event["body"]))
            if (
                entry.path != name[:-5] + ".bin"
                or type(row.get("bytes")) is not int
                or (row["bytes"], row.get("sha256")) != (entry.size_bytes, entry.sha256)
                or row.get("body_complete") is not True
            ):
                raise EvidenceIntegrityError(
                    "Native response lost complete original body pin"
                )
            body = files.pinned(entry, control)
            if index in bodies and bodies[index] != body:
                raise EvidenceIntegrityError("Original native response was replaced")
            bodies[index] = body
        rows[index] = row
    ordered = [rows[i] for i in range(len(rows))]
    if set(bodies) != set(rows) or any(
        r.get("status") != "response_received" or r.get("body_complete") is not True
        for r in ordered
    ):
        raise EvidenceIntegrityError("Native response sequence is unfinished")
    if any(
        type(r.get("bytes")) is not int
        or (r["bytes"], r.get("sha256"))
        != (
            len(bodies[r["request_index"]]),
            hashlib.sha256(bodies[r["request_index"]]).hexdigest(),
        )
        or type(r.get("content_type")) is not str
        for r in ordered
    ):
        raise EvidenceIntegrityError(
            "Native final response metadata differs from complete bytes"
        )
    return ordered, bodies


def complete_batch(
    files: TerminalFiles,
    request_id: str,
    bounds: Bounds,
    parent: bytes,
    payload: bytes,
    summary: object,
    control: OperationControl,
) -> None:
    if CAP_ERROR.fullmatch(parent) is None:
        raise EvidenceIntegrityError("Only original 50000 cap400 permits subdivision")
    rows, bodies = transport_events(files, request_id + "-batch", control)
    paths: dict[tuple[int, ...], dict[str, Any]] = {}
    leaves = []
    for row in rows:
        path = row.get("split_path")
        if (
            type(path) is not list
            or len(path) > 20
            or any(type(p) is not int or p not in (0, 1) for p in path)
        ):
            raise EvidenceIntegrityError("Original native subdivision path malformed")
        key = tuple(path)
        if (
            key in paths
            or row.get("parent_split_path") != (path[:-1] if path else None)
            or type(row.get("depth")) is not int
            or row["depth"] != len(path)
        ):
            raise EvidenceIntegrityError(
                "Native subdivision changed original parent/depth"
            )
        paths[key] = row
    if () not in paths or paths[()]["request_index"] != 0 or bodies[0] != parent:
        raise EvidenceIntegrityError(
            "Native batch lost its original complete cap response"
        )
    for path, row in paths.items():
        cell = request_bounds(row.get("bounds"))
        expected = (
            bounds
            if not path
            else (
                split_bounds(paths[path[:-1]]["bounds"])[path[-1]]
                if path[:-1] in paths
                else None
            )
        )
        if cell != expected or type(row.get("http_status")) is not int:
            raise EvidenceIntegrityError(
                "Native subdivision changed original request bounds/status"
            )
        body = bodies[row["request_index"]]
        status = row["http_status"]
        if status == 400 and CAP_ERROR.fullmatch(body):
            if (
                type(row.get("native_node_cap")) is not int
                or row["native_node_cap"] != 50000
                or any(path + (child,) not in paths for child in (0, 1))
            ):
                raise EvidenceIntegrityError("Native cap branch has missing children")
        elif status == 200:
            content = row.get("content_type")
            if (
                type(content) is not str
                or content.split(";", 1)[0].strip().lower()
                not in ("application/xml", "text/xml")
                or any(path + (child,) in paths for child in (0, 1))
            ):
                raise EvidenceIntegrityError(
                    "Native leaf is not an original complete XML200"
                )
            leaves.append((cell, body))
        else:
            raise EvidenceIntegrityError("Native batch includes a non-cap failure")
    merged, recomputed = union_xml(bounds, leaves)
    recomputed.update(
        requests=sorted(rows, key=lambda row: tuple(row["split_path"])),
        native_parent_http_status=400,
        no_private_oracle_used_to_construct_union=True,
        each_child_uses_original_native_endpoint=True,
        transport_version="map-native-two-independent-http-clients-v1",
        maximum_independent_http_clients=2,
        playwright_thread_shared=False,
        original_absolute_deadline_renewed=False,
        complete_full_union_required=True,
    )
    # JSON comparison distinguishes bool/int and detects every summary field.
    if merged != payload or json.dumps(
        summary, sort_keys=True, allow_nan=False
    ) != json.dumps(recomputed, sort_keys=True, allow_nan=False):
        raise EvidenceIntegrityError(
            "Original complete adapted union/summary does not recompute"
        )
    control.checkpoint()
