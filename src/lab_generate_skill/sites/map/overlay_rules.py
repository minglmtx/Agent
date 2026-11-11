"""Original selected Map Data/route predicates; evidence binding stays in readers.

Only train/b9101b71aacd51b61f6e: preserve_original_area=False and route retained.
The response argument is the full independent comparison's boolean, after the
original typed request/file provenance has been verified. It is not provenance.
"""

from collections import Counter
from typing import Any
from urllib.parse import parse_qs, urlsplit
from .page_health import MapPageHealth


def local_url(value: object, origin: str) -> bool:
    if not isinstance(value, str):
        return False
    p, base = urlsplit(value), urlsplit(origin)
    return (
        p.scheme in ("http", "https")
        and (p.scheme, p.netloc) == (base.scheme, base.netloc)
        and not p.username
        and not p.password
    )


def overlay_rows(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = state.get("overlays")
    if type(rows) is not list:
        raise ValueError("Original native overlay catalog missing")
    result = {}
    for row in rows:
        if (
            type(row) is not dict
            or type(row.get("label")) is not str
            or not row["label"]
            or any(
                type(row.get(k)) is not bool for k in ("visible", "checked", "disabled")
            )
            or row.get("type") not in ("radio", "checkbox")
            or row["label"] in result
        ):
            raise ValueError("Original native overlay catalog malformed")
        result[row["label"]] = row
    return result


def native_paths_added(initial: dict[str, Any], terminal: dict[str, Any]) -> bool:
    fields = ("d", "stroke", "fill", "class_name")
    try:
        old = Counter(tuple(p[k] for k in fields) for p in initial["rendered_paths"])
        new = Counter(tuple(p[k] for k in fields) for p in terminal["rendered_paths"])
        return (
            sum(
                n
                for p, n in (new - old).items()
                if p[0]
                and p[1].lower() in {"#000000", "#00ff00", "#ff0000", "#3388ff"}
                and "leaflet-interactive" in p[3].split()
            )
            > 0
        )
    except (KeyError, TypeError, AttributeError):
        return False


def selected_transition_checks(
    initial: dict[str, Any],
    terminal: dict[str, Any],
    origin: str,
    *,
    initial_route: dict[str, Any],
    terminal_route: dict[str, Any],
    response_matches: bool,
    served: bool,
    page: MapPageHealth,
) -> dict[str, bool]:
    if (
        any(
            type(v) is not dict
            for v in (initial, terminal, initial_route, terminal_route)
        )
        or type(response_matches) is not bool
        or type(served) is not bool
    ):
        raise TypeError("Exact selected original facts and explicit booleans required")
    page = MapPageHealth.model_validate(page)
    url = terminal.get("url")
    valid = (
        isinstance(url, str)
        and local_url(url, origin)
        and urlsplit(url).path not in ("/login", "/user/new")
        and not urlsplit(url).path.startswith("/__")
        and terminal.get("map_visible") is True
    )
    fields = ("origin", "destination", "engine", "rows", "route_visible")
    checks = dict(
        valid_local_native_map=valid,
        actual_supported_local_layer_changed=False,
        native_selected_control_and_layer_code_agree=False,
        actual_local_response_valid=False,
        native_ajax_and_warning_settled=terminal.get("async_loading") is False
        and terminal.get("data_warning") is False,
        original_current_area_preserved=True,
        original_requested_native_route_preserved=initial_route.get("route_visible")
        is True
        and terminal_route.get("route_visible") is True
        and bool(initial_route.get("rows"))
        and all(initial_route.get(k) == terminal_route.get(k) for k in fields),
        actual_native_leaflet_overlay_active=False,
        actual_reviewed_frontend_served=(
            served if terminal.get("map_visible") is True else False
        ),
        valid_terminal_document=page.http_status is not None
        and 200 <= page.http_status < 300
        and page.error_page is False
        and page.login_page is False,
    )
    try:
        before, after = overlay_rows(initial).get("Map Data"), overlay_rows(
            terminal
        ).get("Map Data")
        link = terminal.get("native_long_link")
        if not isinstance(link, str) or not local_url(link, origin):
            return checks
        p = urlsplit(link)
        values = parse_qs(
            p.fragment if p.path == "/" else p.query, keep_blank_values=True
        )
        if any(k not in ("map", "layers") for k in values) or any(
            len(v) != 1 for v in values.values()
        ):
            return checks
        code = values.get("layers", ["M"])[0] or "M"
        members = terminal.get("native_active_overlays")
        changed = (
            before is not None
            and after is not None
            and before["checked"] is False
            and after["checked"] is True
            and after["disabled"] is False
            and type(members) is dict
            and set(members) == {"Map Notes", "Map Data"}
            and all(type(v) is bool for v in members.values())
            and members["Map Data"] is True
            and "D" in code
        )
        if changed and response_matches and native_paths_added(initial, terminal):
            for key in (
                "actual_supported_local_layer_changed",
                "native_selected_control_and_layer_code_agree",
                "actual_local_response_valid",
                "actual_native_leaflet_overlay_active",
            ):
                checks[key] = True
    except (ValueError, TypeError, AttributeError):
        return checks
    return checks
