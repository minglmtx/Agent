"""Selected original predicates compared with exact archived function bodies."""

import ast
from collections import Counter
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit
import pytest
from lab_generate_skill.sites.map.overlay_rules import selected_transition_checks
from lab_generate_skill.sites.map.page_health import MapPageHealth
from test_map_page_health import health

ROOT = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-intake-20261029-v1"
)


def original_functions() -> dict[str, Any]:
    capsule = json.loads(
        (
            Path(
                "/anvme/workspace/r102bf10-lab-generate-skill/experiments/sft-shared-request-repair-v2/groups/38/runtime/capsule.json"
            )
        ).read_text()
    )
    env: dict[str, Any] = dict(
        Counter=Counter,
        Decimal=Decimal,
        InvalidOperation=InvalidOperation,
        hashlib=hashlib,
        parse_qs=parse_qs,
        urlsplit=urlsplit,
        VERSION="map-original-local-layer-transition-v1",
        UNION_VERSION="fixture-union-version",
        LOCAL_OVERLAYS={"Map Notes": "N", "Map Data": "D"},
    )
    for member, names in [
        ("map_native_request_bounds.py", {"bounds_coordinate", "bbox"}),
        ("map_typed_information_share.py", {"local_url", "layer_code"}),
        ("map_local_surface_controls.py", {"health", "label_rows"}),
        (
            "map_native_layer_completion.py",
            {
                "_request",
                "_comparison_valid",
                "_paths_added",
                "layer_transition_checks",
            },
        ),
    ]:
        key = "src/lab_generate_skill/" + member
        raw = (ROOT / "original-capsule" / key).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == capsule["members"][key]["sha256"]
        tree = ast.parse(raw)
        chosen: list[ast.stmt] = [
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names
        ]
        assert {n.name for n in chosen if isinstance(n, ast.FunctionDef)} == names
        exec(compile(ast.Module(body=chosen, type_ignores=[]), key, "exec"), env)
    env["artifact"] = SimpleNamespace(bbox=env["bbox"])
    return env


def surfaces() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    a: dict[str, Any] = dict(
        url="http://map.local/directions",
        map_visible=True,
        overlays=[
            dict(
                label="Map Data",
                visible=True,
                checked=False,
                disabled=False,
                type="checkbox",
            )
        ],
        native_long_link="http://map.local/#map=15/40.77/-73.97",
        rendered_paths=[],
        native_active_overlays={"Map Notes": False, "Map Data": False},
        async_loading=False,
        data_warning=False,
    )
    b = deepcopy(a)
    b["overlays"][0]["checked"] = True
    b["native_long_link"] += "&layers=D"
    b["native_active_overlays"]["Map Data"] = True
    b["rendered_paths"] = [
        dict(
            d="M1,2L3,4",
            stroke="#3388ff",
            fill="none",
            class_name="leaflet-interactive",
        )
    ]
    route = dict(
        origin="Central Park",
        destination="Times Square",
        engine="fossgis_osrm_car",
        rows=["Original instruction"],
        route_visible=True,
    )
    return a, b, route


@pytest.mark.parametrize(
    "case",
    [
        "native",
        "union",
        "no-response",
        "unchanged",
        "disabled",
        "membership",
        "route",
        "route-empty",
        "pending",
        "warning",
        "route-color",
        "no-path",
        "foreign",
        "login",
        "status-missing",
        "server-error",
        "served-missing",
        "duplicate-label",
        "bad-label",
        "hidden-control",
    ],
)
def test_selected_rules_match_original_functions(case: str) -> None:
    old = original_functions()
    a, b, route = surfaces()
    last = deepcopy(route)
    page = health()
    served = True
    response = case != "no-response"
    kind = "union" if case == "union" else "native"
    if case == "unchanged":
        a["overlays"][0]["checked"] = True
    if case == "disabled":
        b["overlays"][0]["disabled"] = True
    if case == "membership":
        b["native_active_overlays"]["Map Data"] = False
    if case == "route":
        last["origin"] = "Other"
    if case == "route-empty":
        route["rows"] = []
    if case == "pending":
        b["async_loading"] = True
    if case == "warning":
        b["data_warning"] = True
    if case == "route-color":
        b["rendered_paths"][0]["stroke"] = "#03f"
    if case == "no-path":
        b["rendered_paths"] = []
    if case == "foreign":
        b["url"] = "http://other.local/"
    if case == "login":
        page["login_page"] = True
    if case == "status-missing":
        page.update(http_status=None, status_source="unavailable")
    if case == "server-error":
        page.update(http_status=503, error_page=True)
    if case == "served-missing":
        served = False
    if case == "duplicate-label":
        b["overlays"] *= 2
    if case == "bad-label":
        b["overlays"][0]["checked"] = 1
    if case == "hidden-control":
        b["overlays"][0]["visible"] = False
    got = selected_transition_checks(
        a,
        b,
        "http://map.local",
        initial_route=route,
        terminal_route=last,
        response_matches=response,
        served=served,
        page=MapPageHealth.model_validate(page),
    )
    payload = b"unit fixture only; original predicate never parses bytes here"
    keys = {
        "serialized_original_bounds",
        "node_ids",
        "node_versions_geometry_tags_members",
        "way_ids",
        "way_versions_geometry_tags_members",
        "relation_ids",
        "relation_versions_geometry_tags_members",
    }
    comparison = dict(
        version=old["UNION_VERSION"],
        passed=response,
        checks={k: True for k in keys},
        api_payload_constructed_expected_reference=False,
        native_single_map_http200_claim=kind == "native",
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )
    args = dict(data_comparison=comparison, data_body=payload)
    bounds = ["-74", "40", "-73.9", "40.1"]
    if kind == "native":
        args["data_record"] = dict(
            method="GET",
            resource_type="xhr",
            http_status=200,
            url="http://map.local/api/0.6/map?bbox=" + ",".join(bounds),
            content_type="application/xml",
        )
    else:
        args["data_transport"] = dict(
            version=old["UNION_VERSION"],
            native_parent_http_status=400,
            native_node_limit_changed=False,
            native_single_request_success=False,
            coverage={
                k: True
                for k in (
                    "all_cells_within_original",
                    "interiors_disjoint",
                    "exact_original_area_covered",
                )
            },
            each_child_uses_original_native_endpoint=True,
            sha256=hashlib.sha256(payload).hexdigest(),
            bounds=bounds,
        )
    expected = old["layer_transition_checks"](
        dict(
            version=old["VERSION"],
            kind="native_map_data",
            allowed_local_overlay_labels=["Map Data"],
            preserve_original_area=False,
            retain_original_native_route=True,
        ),
        a,
        b,
        "http://map.local",
        initial_route=route,
        terminal_route=last,
        require_native_membership=True,
        **args,
    )
    expected.update(
        actual_reviewed_frontend_served=served if b["map_visible"] is True else False,
        valid_terminal_document=type(page["http_status"]) is int
        and 200 <= page["http_status"] < 300
        and page["error_page"] is False
        and page["login_page"] is False,
    )
    assert got == expected
    assert all(got.values()) == (case in ("native", "union", "hidden-control"))


@pytest.mark.parametrize("value", [None, [], True, "", 0])
def test_rules_reject_nonobject_facts(value: Any) -> None:
    a, b, route = surfaces()
    with pytest.raises(TypeError):
        selected_transition_checks(
            value,
            b,
            "http://map.local",
            initial_route=route,
            terminal_route=route,
            response_matches=False,
            served=True,
            page=MapPageHealth.model_validate(health()),
        )
