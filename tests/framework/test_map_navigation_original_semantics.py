"""Selected original oracle comparison; no model/site/native query or source admission."""

from copy import deepcopy
from typing import Any, Protocol, cast
from pathlib import Path
import pytest
from lab_generate_skill.site_navigation_rules import (
    evaluate_navigation as original_evaluate_navigation,
)
from lab_generate_skill.site_result_guard import (
    guard_site_result as original_guard_site_result,
)
from lab_generate_skill.sites.map.navigation_rules import navigation_outcome
from map_navigation_fixtures import SOURCES, ORIGIN, navigation_case


class NavigationOracle(Protocol):
    def __call__(
        self, native: dict[str, Any], page: Any, *, site_origin: str
    ) -> dict[str, Any]: ...


class GuardOracle(Protocol):
    def __call__(
        self,
        judgment: dict[str, Any],
        *,
        runtime_error: Any,
        selected_records_unchanged: bool,
    ) -> dict[str, Any]: ...


evaluate_navigation = cast(NavigationOracle, original_evaluate_navigation)
guard_site_result = cast(GuardOracle, original_guard_site_result)


def page_for(source: str) -> dict[str, Any]:
    c = navigation_case(source)
    page: dict[str, Any] = dict(
        url=ORIGIN + "/communities",
        http_status=200,
        title="OpenStreetMap",
        heading_texts=["Communities"],
        login_page=False,
        error_page=False,
    )
    if source == SOURCES[1]:
        route = c.native["completion"]["map_route"]
        pair = ";".join(",".join(map(str, point)) for point in route["pair"])
        page.update(
            url=ORIGIN + "/directions?engine=fossgis_osrm_car&route=" + pair,
            heading_texts=["Directions"],
            map_route=deepcopy(route["alternatives"][0]["native"]),
        )
    return page


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize(
    "case",
    [
        "success",
        "wrong-path",
        "heading-missing",
        "404",
        "500",
        "login",
        "missing",
        "bad-status",
        "foreign",
        "loading",
    ],
)
@pytest.mark.parametrize("protected", [True, False])
def test_original_navigation_and_guard_match_on_success_failure_and_unknown(
    source: str, case: str, protected: bool
) -> None:
    c = navigation_case(source)
    page = page_for(source)
    if case == "wrong-path":
        page["url"] = ORIGIN + "/about"
    elif case == "heading-missing":
        page["heading_texts"] = []
    elif case == "404":
        page.update(http_status=404, error_page=True)
    elif case == "500":
        page["http_status"] = 503
    elif case == "login":
        page["login_page"] = True
    elif case == "missing":
        page.pop("title")
    elif case == "bad-status":
        page["http_status"] = True
    elif case == "foreign":
        page["url"] = page["url"].replace(ORIGIN, "http://other:12001")
    elif case == "loading" and source == SOURCES[1]:
        page["map_route"]["loading"] = True
    expected = guard_site_result(
        evaluate_navigation(c.native, page, site_origin=ORIGIN),
        runtime_error=None,
        selected_records_unchanged=protected,
    )
    actual = navigation_outcome(
        c.load().private_spec,
        page,
        site_origin=ORIGIN,
        runtime_error=False,
        selected_records_unchanged=protected,
    )
    assert actual.original_result() == expected
    assert navigation_outcome(
        c.load().private_spec,
        page,
        site_origin=ORIGIN,
        runtime_error=True,
        selected_records_unchanged=protected,
    ).original_result() == guard_site_result(
        expected,
        runtime_error={"error": "unknown action"},
        selected_records_unchanged=protected,
    )


@pytest.mark.parametrize(
    "case",
    [
        "reversed",
        "foot",
        "unsubmitted",
        "rows",
        "summary",
        "line",
        "missing-route",
        "missing-field",
        "bad-rows",
        "hidden-form",
        "rounded",
    ],
)
def test_original_directions_semantics_require_order_mode_full_content_and_real_line(
    case: str,
) -> None:
    c = navigation_case(SOURCES[1])
    page = page_for(SOURCES[1])
    state = page["map_route"]
    if case == "reversed":
        route = c.native["completion"]["map_route"]
        page["url"] = (
            ORIGIN
            + "/directions?engine=fossgis_osrm_car&route="
            + ";".join(",".join(map(str, p)) for p in reversed(route["pair"]))
        )
    elif case == "foot":
        page["url"] = page["url"].replace("osrm_car", "osrm_foot")
    elif case == "unsubmitted":
        state.update(rows=[], summary="", route_visible=False)
    elif case == "rows":
        state["rows"] = state["rows"][:-1]
    elif case == "summary":
        state["summary"] += " foreign route"
    elif case == "line":
        state["route_visible"] = False
    elif case == "missing-route":
        page.pop("map_route")
    elif case == "missing-field":
        state.pop("rows")
    elif case == "bad-rows":
        state["rows"] = [None]
    elif case == "hidden-form":
        state.update(origin="", destination="", engine="", route_form_visible=False)
    else:
        pair = c.native["completion"]["map_route"]["pair"]
        page["url"] = (
            ORIGIN
            + "/directions?engine=fossgis_osrm_car&route="
            + ";".join(",".join(f"{x:.4f}" for x in p) for p in pair)
        )
    expected = evaluate_navigation(c.native, page, site_origin=ORIGIN)
    actual = navigation_outcome(
        c.load().private_spec,
        page,
        site_origin=ORIGIN,
        runtime_error=False,
        selected_records_unchanged=True,
    )
    assert actual.original_result() == expected
    assert actual.status == (
        "success"
        if case in ("hidden-form", "rounded")
        else (
            "unknown"
            if case in ("missing-route", "missing-field", "bad-rows")
            else "failure"
        )
    )


@pytest.mark.parametrize("bad", [None, 1, "false", [], {}])
def test_unknown_or_wrong_type_protection_cannot_claim_unchanged(bad: Any) -> None:
    c = navigation_case()
    with pytest.raises(TypeError):
        navigation_outcome(
            c.load().private_spec,
            page_for(SOURCES[0]),
            site_origin=ORIGIN,
            runtime_error=False,
            selected_records_unchanged=bad,
        )


@pytest.mark.parametrize("source", SOURCES)
def test_current_private_evidence_roundtrip_to_inputs_and_original_judgment(
    source: str, tmp_path: Path
) -> None:
    from evidence_control_fixtures import EvidenceFixtureStore
    from lab_generate_skill.domain.evidence import EvidenceMetadata
    from lab_generate_skill.bootstrap.map_navigation import load_navigation_inputs
    from test_slurm_commands import guard

    c = navigation_case(source)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir(mode=0o700)
    store = EvidenceFixtureStore(evidence_root)
    ref = store.put(
        c.raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="map-native-contract/1",
            visibility="private",
            producer="unit-map-navigation",
        ),
        guard(30),
    )
    value = load_navigation_inputs(
        store.read(ref, guard(30)), ref, c.public, binding=c.binding
    )
    assert value.private_spec.native_contract_ref == ref and ref.visibility == "private"
    page = page_for(source)
    assert navigation_outcome(
        value.private_spec,
        page,
        site_origin=ORIGIN,
        runtime_error=False,
        selected_records_unchanged=True,
    ).original_result() == evaluate_navigation(c.native, page, site_origin=ORIGIN)
