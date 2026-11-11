"""Independent original navigation readiness proof; no initializer or page I/O."""

import math
import re
from urllib.parse import urlsplit, parse_qs
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .navigation_initial_evidence import NavigationInitialReadiness
from .navigation_initial_rules import (
    same_start_document,
    navigation_readiness_arguments,
)
from .native_view_rules import ready_signal, native_zoom
from .state_rules import object_json


def original_navigation_readiness(
    proof: NavigationInitialReadiness, task: PublicTask
) -> None:
    proof = NavigationInitialReadiness.model_validate(proof)
    proof.initialization.check_task(task)
    h = proof.page.health
    if (
        proof.start_url != task.start_url
        or not same_start_document(task, h.url)
        or proof.page.document_state != "complete"
        or h.http_status is None
        or not 200 <= h.http_status < 300
        or h.login_page
        or h.error_page
        or proof.stable_seconds > 45
    ):
        raise EvidenceIntegrityError(
            "Original navigation initial document/readiness changed"
        )
    start = urlsplit(task.start_url)
    if start.path in ("/communities", "/traces"):
        if (
            proof.native_signal_json is not None
            or proof.native_view_json is not None
            or proof.stable_seconds != 0
        ):
            raise EvidenceIntegrityError(
                "Ordinary original document cannot assert map readiness"
            )
        return
    if (
        start.path not in ("/", "/search", "/directions")
        or proof.native_signal_json is None
        or proof.native_view_json is None
        or proof.stable_seconds < 0.75
    ):
        raise EvidenceIntegrityError(
            "Original complete plain-map initial evidence required"
        )
    args = navigation_readiness_arguments(task)
    signal = ready_signal(
        object_json(proof.native_signal_json.encode()), directions=args["directions"]
    )
    view = object_json(proof.native_view_json.encode())
    zoom = native_zoom(view)
    if (
        view["map_visible"] is not True
        or signal["ready"] is not True
        or signal["busy"]
        or signal["loading"]
        or signal["geo"] != view["native_geo_uri"]
        or signal["long"] != view["native_long_link"]
    ):
        raise EvidenceIntegrityError(
            "Original plain-map view did not settle consistently"
        )
    if args["directions"]:
        fields = signal["directionsFields"]
        selectors = (
            "input[name=route_from]",
            "input[name=route_to]",
            "select.routing_engines",
        )
        if (
            signal["directionsContent"] is not True
            or len(fields) != 3
            or any(
                type(f) is not dict
                or set(f) != {"selector", "total", "visible"}
                or f["selector"] != selector
                or type(f["total"]) is not int
                or type(f["visible"]) is not int
                or f["visible"] < 0
                or f["total"] < f["visible"]
                or (not args["routeRequest"] and f["visible"] != 1)
                for f, selector in zip(fields, selectors)
            )
        ):
            raise EvidenceIntegrityError(
                "Original directions controls/outcome not ready"
            )
    m = re.fullmatch(
        r"geo:([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)\?z=(\d+)", signal["geo"]
    )
    if m is None:
        raise EvidenceIntegrityError("Original native geographic signal invalid")
    actual_lat, actual_lon = float(m[1]), float(m[2])
    # Search/directions auto-pan is an original initialization behavior. Bind
    # settled native signals to each other; only plain map fixes the start center.
    if start.path != "/":
        recorded = parse_qs(urlsplit(signal["long"]).fragment).get("map", [])
        if (
            len(recorded) != 1
            or re.fullmatch(r"\d+/[-+]?\d+(?:\.\d+)?/[-+]?\d+(?:\.\d+)?", recorded[0])
            is None
        ):
            raise EvidenceIntegrityError("Original auto-pan native range is incomplete")
        z, a, b = map(float, recorded[0].split("/"))
        if (
            not all(math.isfinite(v) for v in (z, a, b, actual_lat, actual_lon))
            or not -90 <= actual_lat <= 90
            or not -180 <= actual_lon <= 180
            or z != zoom
            or abs(a - actual_lat) > 1e-9
            or abs(((b - actual_lon + 180) % 360) - 180) > 1e-9
        ):
            raise EvidenceIntegrityError("Original auto-pan native signals disagree")
        return
    wanted = parse_qs(start.fragment).get("map", [])
    recorded = parse_qs(urlsplit(signal["long"]).fragment).get("map", [])
    pattern = r"\d+/[-+]?\d+(?:\.\d+)?/[-+]?\d+(?:\.\d+)?"
    if (
        len(wanted) != 1
        or len(recorded) != 1
        or any(re.fullmatch(pattern, v) is None for v in (wanted[0], recorded[0]))
    ):
        raise EvidenceIntegrityError(
            "Original native/declared map ranges are incomplete"
        )
    expected_zoom, expected_lat, expected_lon = map(float, wanted[0].split("/"))
    recorded_zoom, recorded_lat, recorded_lon = map(float, recorded[0].split("/"))
    if (
        not all(
            math.isfinite(v)
            for v in (
                expected_zoom,
                expected_lat,
                expected_lon,
                recorded_zoom,
                recorded_lat,
                recorded_lon,
            )
        )
        or not 0 <= expected_zoom <= 30
    ):
        raise EvidenceIntegrityError(
            "Original initial map coordinates must be finite and bounded"
        )
    tolerance = 0.5 * 10 ** -max(0, math.ceil(math.log2(max(expected_zoom, 1)))) + 1e-9

    def distance(a: float, b: float) -> float:
        return abs(((a - b + 180) % 360) - 180)

    if (
        not all(
            math.isfinite(v)
            for v in (
                actual_lat,
                actual_lon,
                expected_zoom,
                expected_lat,
                expected_lon,
                recorded_zoom,
                recorded_lat,
                recorded_lon,
            )
        )
        or not -90 <= expected_lat <= 90
        or not -180 <= expected_lon <= 180
        or zoom != expected_zoom
        or zoom != recorded_zoom
        or abs(recorded_lat - actual_lat) > 1e-9
        or distance(recorded_lon, actual_lon) > 1e-9
        or abs(expected_lat - actual_lat) > tolerance
        or distance(expected_lon, actual_lon) > tolerance
    ):
        raise EvidenceIntegrityError(
            "Original initial center/zoom and native links disagree"
        )
