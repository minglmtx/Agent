"""Select original full-area requests for independent DB capture; no query effects."""

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Literal
from urllib.parse import urlsplit
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .terminal_evidence import TerminalMapEvidence
from .terminal_transport import transport_events, complete_batch
from .state_rules import object_json
from .native_bounds import Bounds, request_bounds
from .native_route_request import selected_bounds
from .native_xml import parse_native_xml
from .tasks.overlay_reference_policy import full_original_bbox_retained


@dataclass(frozen=True)
class MapReferenceCandidate:
    index: int
    request_id: str
    bounds: Bounds
    response_kind: Literal["native_200", "adapted_union"]
    payload: ReleaseFile
    body: bytes
    records_sha256: str


@dataclass(frozen=True)
class MapReferenceCandidates:
    selected: tuple[MapReferenceCandidate, ...]
    skipped: tuple[tuple[int, str], ...]


def reference_candidates(
    terminal: TerminalMapEvidence, control: OperationControl
) -> MapReferenceCandidates:
    files = terminal.files
    closed = object_json(files.read("map-process-close.json", control))
    count = closed["request_count"]
    expected = [f"request-{i}-browser-start.json" for i in range(count)]
    actual = sorted(n for n in files.members if n.endswith("-browser-start.json"))
    if sorted(expected) != actual:
        raise EvidenceIntegrityError(
            "Terminal native request set differs from original closure"
        )
    url = urlsplit(terminal.initial.prepared.public_task.start_url)
    origin = url.scheme + "://" + url.netloc
    selected = []
    skipped = []
    for index in range(count):
        control.checkpoint()
        request_id = f"request-{index}"
        start = object_json(files.read(request_id + "-browser-start.json", control))
        raw_bounds = selected_bounds(
            origin,
            start.get("actual_url"),
            start.get("method"),
            start.get("resource_type"),
        )
        bounds = request_bounds(raw_bounds)
        if (
            start.get("schema_version") != "map-actual-browser-native-request/1"
            or start.get("plan_sha256") != terminal.publication.plan.digest
            or start.get("request_id") != request_id
            or start.get("requested_bbox_strings") != list(raw_bounds or ())
            or start.get("native_scope_or_cap_changed") is not False
            or type(start.get("native_request_budget_seconds")) is not int
            or start["native_request_budget_seconds"] != 300
        ):
            raise EvidenceIntegrityError(
                "Map terminal request changed original browser selection"
            )
        before = start.get("last_unique_observation_sequence")
        deadline = start.get("original_absolute_monotonic_deadline")
        if (
            not isinstance(deadline, (int, float))
            or isinstance(deadline, bool)
            or not math.isfinite(deadline)
            or deadline <= 0
        ):
            raise EvidenceIntegrityError(
                "Original native request deadline is malformed"
            )
        if before is not None and (
            type(before) is not int or not 0 <= before <= terminal.publication.sequence
        ):
            raise EvidenceIntegrityError("Original request points to an absent readout")
        ended = object_json(files.read(request_id + "-browser-end.json", control))
        registration = object_json(
            files.read(request_id + "-registration.json", control)
        )
        if (
            ended.get("continue_returned") is not True
            or ended.get("error") is not None
            or registration.get("schema_version") != "map-native-relay-registration/1"
            or registration.get("request_id") != request_id
            or registration.get("original_origin") != origin
            or request_bounds(registration.get("bounds")) != bounds
            or registration.get("original_absolute_monotonic_deadline")
            != start.get("original_absolute_monotonic_deadline")
            or registration.get("dispatch_on_first_private_get_only") is not True
            or registration.get("actual_browser_provenance_verified") is not False
        ):
            raise EvidenceIntegrityError(
                "Original browser request/relay registration incomplete"
            )
        delivery = object_json(files.read(request_id + "-delivery-start.json", control))
        finish = object_json(files.read(request_id + "-delivery-end.json", control))
        pin = ReleaseFile.model_validate_json(json.dumps(delivery.get("payload")))
        body = files.pinned(pin, control)
        if (
            pin.path != request_id + "-response.bin"
            or finish.get("delivery_complete") is not True
            or finish.get("exchange_state") != "complete"
            or finish.get("errors") != []
            or type(finish.get("delivered_bytes")) is not int
            or finish["delivered_bytes"] != len(body)
        ):
            raise EvidenceIntegrityError(
                "Native delivery lacks complete original bytes"
            )
        rows, bodies = transport_events(files, request_id + "-first", control)
        row = rows[0]
        status = row.get("http_status")
        if (
            len(rows) != 1
            or type(status) is not int
            or request_bounds(row.get("bounds")) != bounds
            or row.get("split_path") != []
            or row.get("parent_split_path") is not None
            or type(row.get("depth")) is not int
            or row["depth"] != 0
            or type(delivery.get("original_http_status")) is not int
            or delivery["original_http_status"] != status
        ):
            raise EvidenceIntegrityError(
                "Native delivery changed its original response"
            )
        adapted = delivery.get("adapted")
        if (
            type(adapted) is not bool
            or type(delivery.get("delivered_http_status")) is not int
        ):
            raise EvidenceIntegrityError("Explicit native/adapted status required")
        if adapted:
            if (
                status != 400
                or delivery["delivered_http_status"] != 200
                or delivery.get("native_original_http200_claim") is not False
            ):
                raise EvidenceIntegrityError(
                    "Adapted response cannot claim original native200"
                )
            complete_batch(
                files,
                request_id,
                bounds,
                bodies[0],
                body,
                delivery.get("batch"),
                control,
            )
            kind: Literal["native_200", "adapted_union"] = "adapted_union"
        else:
            if (
                delivery["delivered_http_status"] != status
                or delivery.get("native_original_http200_claim") is not (status == 200)
                or delivery.get("batch") is not None
                or body != bodies[0]
            ):
                raise EvidenceIntegrityError(
                    "Unadapted native response changed original bytes/status"
                )
            if status != 200:
                skipped.append((index, "original_native_non200"))
                continue
            kind = "native_200"
        if not full_original_bbox_retained(bounds, terminal.original_bounds):
            skipped.append((index, "original_reference_area_narrowed"))
            continue
        if kind == "native_200":
            parse_native_xml(body)
        pins = [
            f.model_dump(mode="json")
            for n, f in sorted(files.members.items())
            if n.startswith(request_id + "-")
        ]
        digest = hashlib.sha256(
            json.dumps(
                pins, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        selected.append(
            MapReferenceCandidate(index, request_id, bounds, kind, pin, body, digest)
        )
    return MapReferenceCandidates(tuple(selected), tuple(skipped))
