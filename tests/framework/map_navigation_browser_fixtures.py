"""Passive navigation page/clock doubles, not a website or source permission."""

from typing import Any
from urllib.parse import urlsplit, parse_qs
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.map.navigation_page_capture import PAGE
from lab_generate_skill.sites.map.native_view_scripts import READ, READINESS
from map_browser_initialization_fixtures import Clock as Clock
from map_navigation_fixtures import navigation_case
from test_core_contracts import reference
from lab_generate_skill.domain.errors import OperationStopped


class CancelledControl:
    def checkpoint(self) -> float:
        raise OperationStopped("CANCELLED", "navigation-browser-unit")

    def wait(self, seconds: float) -> None:
        self.checkpoint()


def selection(source: str) -> tuple[MapNavigationInitialization, PublicTask]:
    c = navigation_case(source)
    return (
        MapNavigationInitialization(
            endpoint="http://127.0.0.1:12001/",
            prepared_ref=reference("private", "prepared-task/1"),
            site_ref=reference("private", "site-resource-started/1"),
            native_contract_sha256=c.load().private_spec.native_contract_ref.sha256,
        ),
        c.public,
    )


class Page:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.url = "about:blank"
        self.calls: list[str] = []
        self.fault = ""
        self.status: int | None = 200
        self.headings: list[str] = ["Original initial heading"]
        self.arguments: dict[str, Any] | None = None

    def goto(self, url: str, *, timeout: float) -> None:
        assert 0 < timeout <= 10000
        self.calls.append("goto:" + url)
        self.url = url
        if self.fault == "goto":
            raise RuntimeError("Original partial goto failure")
        if self.fault == "redirect":
            self.url += "&changed=1"

    def wait_for_function(
        self, program: str, *, timeout: float, arg: dict[str, Any] | None = None
    ) -> None:
        assert timeout > 0
        self.calls.append("wait")
        self.arguments = arg
        if arg is not None:
            assert arg["directions"] is False and arg["routeRequest"] is False
        if self.fault == "wait":
            raise TimeoutError("Original native map wait failure")

    def wait_for_timeout(self, milliseconds: float) -> None:
        self.clock.elapsed += milliseconds / 1000

    def evaluate(self, program: str, arg: dict[str, Any] | None = None) -> Any:
        self.calls.append("sample")
        if program in (READ, READINESS):
            map_value = parse_qs(urlsplit(self.url).fragment)["map"][0]
            zoom, lat, lon = map_value.split("/")
            geo = f"geo:{lat},{lon}?z={zoom}"
            if program == READINESS:
                return dict(
                    geo=geo,
                    long="/#map=" + map_value,
                    classes="leaflet-container",
                    busy=False,
                    loading=False,
                    directionsContent=None,
                    directionsFields=None,
                    ready=("wrong" if self.fault == "signal" else True),
                )
            return dict(
                map_visible=True,
                native_geo_uri=geo,
                native_long_link="/#map=" + map_value,
            )
        assert program == PAGE
        if self.fault == "capture":
            raise OSError("Original passive capture failed")
        result = dict(
            schema_version="map-navigation-page-health/1",
            health=dict(
                schema_version="map-page-health/1",
                url=self.url,
                sampled_url=self.url,
                title="OpenStreetMap",
                http_status=self.status,
                status_source=(
                    "unavailable" if self.status is None else "navigation_timing"
                ),
                login_page=False,
                error_page=False,
            ),
            heading_texts=list(self.headings),
            document_state="complete",
        )
        if self.fault == "document-changed":
            self.url = "http://127.0.0.1:12001/help"
        return result
