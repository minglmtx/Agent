"""Independently validate original passive directions readiness, without page I/O."""

import json
import math
import re
from urllib.parse import parse_qs, urlsplit
from typing import Any
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from .native_view_rules import selected_public, ready_signal, native_zoom
from .state_rules import object_json


def original_readiness(
    raw: bytes, initialization: MapNativeInitialization, task: PublicTask
) -> dict[str, Any]:
    initialization.check_task(task)
    selected_public(task)
    value = object_json(raw)
    if set(value) != {
        "schema_version",
        "initialization",
        "public_task",
        "native_readiness",
        "native_view",
        "stable_seconds",
        "new_observation_created",
        "task_success_or_admission_claim",
    } or (
        value["schema_version"] != "map-native-initial-readiness/1"
        or value["initialization"] != initialization.model_dump(mode="json")
        or value["public_task"] != task.model_dump(mode="json")
        or value["new_observation_created"] is not False
        or value["task_success_or_admission_claim"] is not False
    ):
        raise EvidenceIntegrityError("Original selected Map readiness fields changed")
    if (
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        != raw
    ):
        raise EvidenceIntegrityError("Noncanonical original Map readiness fact")
    seconds = value["stable_seconds"]
    if (
        type(seconds) not in (int, float)
        or not math.isfinite(seconds)
        or not 0.75 <= seconds <= 45
    ):
        raise EvidenceIntegrityError("Original native stability interval missing")
    signal = ready_signal(value["native_readiness"])
    view = value["native_view"]
    native_zoom(view)
    if (
        not isinstance(view, dict)
        or view["map_visible"] is not True
        or (
            signal["ready"] is not True
            or signal["busy"]
            or signal["loading"]
            or signal["directionsContent"] is not True
            or signal["geo"] != view["native_geo_uri"]
            or signal["long"] != view["native_long_link"]
        )
    ):
        raise EvidenceIntegrityError(
            "Original native map did not report settled directions"
        )
    # Same original readiness agreement: allow directions auto-pan and longitude wrap.
    match = re.fullmatch(
        r"geo:([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)\?z=(\d+)", signal["geo"]
    )
    assert match is not None
    values = parse_qs(urlsplit(signal["long"]).fragment).get("map", [])
    if len(values) != 1 or not re.fullmatch(
        r"\d+/[-+]?\d+(?:\.\d+)?/[-+]?\d+(?:\.\d+)?", values[0]
    ):
        raise EvidenceIntegrityError("Original native long link is malformed")
    zoom, lat, lon = map(float, values[0].split("/"))
    expected_lat, expected_lon = float(match[1]), float(match[2])
    if (
        not all(math.isfinite(v) for v in (zoom, lat, lon))
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
        or (
            zoom != int(match[3])
            or abs(lat - expected_lat) > 1e-9
            or abs(((lon - expected_lon + 180) % 360) - 180) > 1e-9
        )
    ):
        raise EvidenceIntegrityError("Original native geographic links disagree")
    return value
