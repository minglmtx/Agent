"""Original pure route checks; native I/O stays in collectors.

Bodies retained from map_route.py ac6e27fc, the selected87afb capsule.
Only type annotations and formatting differ; no legacy runner import.
"""

import math
import re
import urllib.parse
from typing import Any, Callable

LABELS = {"car": "Car (OSRM)", "bike": "Bicycle (OSRM)", "foot": "Foot (OSRM)"}


def normalized(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_point(text: Any) -> list[float] | None:
    try:
        values = [float(x.strip()) for x in text.split(",")]
        if len(values) != 2 or not all(math.isfinite(x) for x in values):
            return None
        return values
    except (ValueError, TypeError, AttributeError):
        return None


def pair_equal(a: Any, b: Any) -> bool:
    return len(a) == len(b) == 2 and all(
        x is not None
        and y is not None
        and len(x) == len(y) == 2
        and all(abs(v - w) < 1e-8 for v, w in zip(x, y))
        for x, y in zip(a, b)
    )


def native_rounded_point(text: Any, point: Any) -> bool:
    """OSM directions.js writes toFixed(zoomPrecision) coordinates to the URL.

    This is only used with named-place identity AND exact native route content;
    it must never serve as a standalone place or route success check.
    """
    if not isinstance(text, str) or len(point) != 2:
        return False
    pieces = text.split(",")
    if len(pieces) != 2:
        return False
    for token, value in zip(pieces, point):
        m = re.fullmatch(r"\s*[+-]?\d+(?:\.(\d{1,8}))?\s*", token)
        if not m:
            return False
        digits = len(m.group(1) or "")
        if abs(float(token) - value) > 0.5 * 10 ** (-digits) + 1e-10:
            return False
    return True


def route_checks(spec: dict[str, Any], state: Any, url: str) -> dict[str, bool]:
    required = {
        "origin",
        "destination",
        "engine",
        "summary",
        "rows",
        "route_visible",
        "loading",
    }
    if not isinstance(state, dict) or not required <= state.keys():
        raise ValueError("Missing native route capture")
    if state["loading"]:
        raise ValueError("Native route was still loading at termination")
    if not isinstance(state["rows"], list) or any(
        not isinstance(x, str) for x in state["rows"]
    ):
        raise ValueError("Malformed route rows")
    params = urllib.parse.parse_qs(
        urllib.parse.urlsplit(url).query, keep_blank_values=True
    )
    declared = params.get("route", [])
    engines = params.get("engine", [])
    pair = (
        [parse_point(x) for x in declared[0].split(";")] if len(declared) == 1 else []
    )
    form_absent = state.get("route_form_visible") is False and all(
        state[k] == "" for k in ("origin", "destination", "engine")
    )
    choices = [
        r
        for r in spec["alternatives"]
        if engines == ["fossgis_osrm_" + r["profile"]]
        and (state["engine"] == LABELS[r["profile"]] or form_absent)
    ]
    same: Callable[[dict[str, Any]], bool] = lambda ref: normalized(
        state["summary"]
    ) == normalized(ref["native"]["summary"]) and [
        normalized(x) for x in state["rows"]
    ] == [
        normalized(x) for x in ref["native"]["rows"]
    ]
    endpoints = pair_equal(pair, spec["pair"]) and pair_equal(
        [parse_point(state["origin"]), parse_point(state["destination"])], spec["pair"]
    )
    if spec.get("endpoint_labels"):
        labels = spec["endpoint_labels"]
        if len(labels) != 2 or any(
            not isinstance(x, list)
            or not x
            or any(not isinstance(y, str) or not y for y in x)
            for x in labels
        ):
            raise ValueError("Missing named-place identity references")
        raw = declared[0].split(";") if len(declared) == 1 else []
        url_ok = len(raw) == 2 and all(
            native_rounded_point(x, p) for x, p in zip(raw, spec["pair"])
        )
        fields = [state["origin"], state["destination"]]
        names_ok = all(
            normalized(x).casefold() in {normalized(y).casefold() for y in names}
            or native_rounded_point(x, p)
            for x, names, p in zip(fields, labels, spec["pair"])
        )
        endpoints = url_ok and names_ok
    if form_absent:
        # Native asynchronous route completion can leave its input form hidden
        # after a sidebar transition. URL alone is insufficient: require the
        # entire rendered reference and visible route as independent evidence.
        url_endpoints = (
            url_ok if spec.get("endpoint_labels") else pair_equal(pair, spec["pair"])
        )
        endpoints = (
            url_endpoints
            and len(choices) == 1
            and bool(state["rows"])
            and same(choices[0])
            and state["route_visible"] is True
        )
    return {
        "route_endpoints": endpoints,
        "route_transport_mode": len(choices) == 1,
        "route_rendered_content": len(choices) == 1
        and bool(state["rows"])
        and same(choices[0]),
        "route_line_displayed": state["route_visible"] is True,
    }
