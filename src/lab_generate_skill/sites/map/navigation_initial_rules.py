"""Original plain-map readiness arguments; no target navigation or control IDs."""

import math
import re
from urllib.parse import urlsplit, parse_qs
from typing import Any
from lab_generate_skill.domain.task import PublicTask


def same_start_document(task: PublicTask, actual_url: str) -> bool:
    original, actual = urlsplit(task.start_url), urlsplit(actual_url)
    return (actual.scheme, actual.netloc, actual.path, actual.query) == (
        original.scheme,
        original.netloc,
        original.path,
        original.query,
    )


def navigation_readiness_arguments(task: PublicTask) -> dict[str, Any]:
    """Same plain-map branch as original map_view.wait_native_view."""
    start = urlsplit(task.start_url)
    plain = start.path == "/"
    if start.path not in ("/", "/search", "/directions") or (plain and start.query):
        raise ValueError(
            "Explicit original map/search/directions initial path required"
        )
    zoom: int | None = None
    lat: float | None = None
    lon: float | None = None
    if plain or start.fragment:
        values = parse_qs(start.fragment).get("map", [])
        if (
            len(values) != 1
            or re.fullmatch(r"\d+/[-+]?\d+(?:\.\d+)?/[-+]?\d+(?:\.\d+)?", values[0])
            is None
        ):
            raise ValueError("Explicit original initial map view required")
        z, a, b = values[0].split("/")
        zoom, lat, lon = int(z), float(a), float(b)
        if not (
            0 <= zoom <= 30
            and math.isfinite(lat)
            and math.isfinite(lon)
            and -90 <= lat <= 90
            and -180 <= lon <= 180
        ):
            raise ValueError("Original map initial coordinates out of bounds")
    return dict(
        search=start.path == "/search",
        expectedZoom=zoom if plain else None,
        expectedCenter={"lat": lat, "lon": lon} if plain else None,
        centerTolerance=0.5 * 10 ** -max(0, math.ceil(math.log2(max(zoom or 1, 1))))
        + 1e-9,
        directions=start.path == "/directions",
        routeRequest=bool(parse_qs(start.query, keep_blank_values=True).get("route")),
    )
