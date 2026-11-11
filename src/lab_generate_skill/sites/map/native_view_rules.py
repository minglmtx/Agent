"""Selected original directions waiting arguments and passive map-link validation."""

import math
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit
from .tasks.overlay_spec import START, GOAL
from lab_generate_skill.domain.task import PublicTask


def selected_public(task: PublicTask) -> None:
    u = urlsplit(task.start_url)
    suffix = (
        u.path
        + ("?" + u.query if u.query else "")
        + ("#" + u.fragment if u.fragment else "")
    )
    if task.goal != GOAL or suffix != START:
        raise ValueError("Original selected public Map goal and start path required")


def original_document(task: PublicTask, actual_url: object) -> bool:
    """Exact original document/route; native readiness separately checks auto-pan.

    The original directions view may change the fragment while fitting its route.
    This check grants no readiness or Actor admission by itself.
    """
    selected_public(task)
    if (
        type(actual_url) is not str
        or not actual_url
        or len(actual_url) > 16384
        or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in actual_url)
    ):
        return False
    try:
        wanted, actual = urlsplit(task.start_url), urlsplit(actual_url)
    except ValueError:
        return False
    return (actual.scheme, actual.netloc, actual.path, actual.query) == (
        wanted.scheme,
        wanted.netloc,
        wanted.path,
        wanted.query,
    )


def readiness_arguments() -> dict[str, Any]:
    # Exact selected branch of original map_view.wait_native_view. Directions
    # retain native auto-pan, not literal route/center/zoom comparisons.
    requested = urlsplit(START)
    values = parse_qs(requested.fragment)["map"][0].split("/")
    zoom = int(values[0])
    return {
        "search": False,
        "expectedZoom": None,
        "expectedCenter": None,
        "centerTolerance": 0.5 * 10 ** -max(0, math.ceil(math.log2(max(zoom, 1))))
        + 1e-9,
        "directions": True,
        "routeRequest": True,
    }


def native_zoom(state: object) -> int:
    if not isinstance(state, dict) or type(state.get("map_visible")) is not bool:
        raise ValueError("Missing native map view capture")
    uri = state.get("native_geo_uri")
    if not isinstance(uri, str):
        raise ValueError("Missing native map Geo URI")
    match = re.fullmatch(r"geo:([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)\?z=(\d+)", uri)
    if not match:
        raise ValueError("Malformed native map Geo URI")
    lat, lon = map(float, match.groups()[:2])
    zoom = int(match[3])
    if not (
        math.isfinite(lat)
        and math.isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
        and 0 <= zoom <= 30
    ):
        raise ValueError("Native map view is outside geographic bounds")
    link = state.get("native_long_link")
    if not isinstance(link, str):
        raise ValueError("Missing native map link")
    values = parse_qs(urlsplit(link).fragment).get("map", [])
    if len(values) != 1:
        raise ValueError("Ambiguous native map link")
    parts = values[0].split("/")
    if len(parts) != 3 or not parts[0].isdigit() or int(parts[0]) != zoom:
        raise ValueError("Native map signals disagree on zoom")
    return zoom


def ready_signal(value: object, *, directions: bool = True) -> dict[str, Any]:
    if type(directions) is not bool:
        raise TypeError("Explicit native readiness branch required")
    if type(value) is not dict or set(value) != {
        "geo",
        "long",
        "classes",
        "busy",
        "loading",
        "directionsContent",
        "directionsFields",
        "ready",
    }:
        raise ValueError("Original complete native readiness signal required")
    if (
        any(type(value[name]) is not bool for name in ("busy", "loading", "ready"))
        or any(type(value[name]) is not str for name in ("geo", "long", "classes"))
        or (
            (
                type(value["directionsContent"]) is not bool
                or type(value["directionsFields"]) is not list
            )
            if directions
            else (
                value["directionsContent"] is not None
                or value["directionsFields"] is not None
            )
        )
    ):
        raise ValueError("Original native readiness signal types changed")
    return value
