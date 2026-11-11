"""Pinned complete42 data for tests; never a source or permission authority."""

import json
from pathlib import Path
from typing import Any
from lab_generate_skill.bootstrap.map_navigation_source import (
    MapNavigationSourceSelection,
)
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSourceBinding
from map_navigation_fixtures import NavigationCase, ORIGIN

ROOT = Path("/anvme/workspace/r102bf10-lab-generate-skill")
PLAN = (
    ROOT
    / "experiments/framework-map-navigation42-production-20261102-v1/group-plan.json"
)
ROWS: tuple[dict[str, Any], ...] = tuple(json.loads(PLAN.read_text())["members"])
SOURCES = tuple(r["source_task_id"] for r in ROWS)


def next_case(source: str = SOURCES[0]) -> NavigationCase:
    row = next(r for r in ROWS if r["source_task_id"] == source)
    raw = Path(row["contract_pin"]["path"]).read_bytes()
    native = json.loads(raw)
    binding = NavigationSourceBinding.model_validate_json(
        json.dumps(row["source_binding"])
    )
    public = PublicTask(
        identity=TaskIdentity(
            source_task_id=source,
            task_id=binding.active_task_id,
            site="map",
            family="navigation_page_identity",
            split="train",
            contract_version=1,
        ),
        goal=native["goal"],
        start_url=ORIGIN + native["start_path"],
        allowed_actions=("click", "send_msg_to_user"),
    )
    return NavigationCase(raw, native, binding, public)


def selected(source: str = SOURCES[0]) -> MapNavigationSourceSelection:
    c = next_case(source)
    return MapNavigationSourceSelection(c.raw, c.binding, c.public)


from map_navigation_browser_fixtures import Page
from lab_generate_skill.sites.map.native_view_scripts import READ, READINESS


class AdditionalStartPage(Page):
    """Passive synthetic auto-pan/ordinary starts; no target or permissions."""

    def wait_for_function(
        self, program: str, *, timeout: float, arg: dict[str, Any] | None = None
    ) -> None:
        assert timeout > 0
        self.calls.append("wait")
        self.arguments = arg
        if self.fault == "wait":
            raise TimeoutError("Original asynchronous map wait failed")

    def evaluate(self, program: str, arg: dict[str, Any] | None = None) -> Any:
        if program not in (READ, READINESS):
            return super().evaluate(program, arg)
        self.calls.append("sample")
        geo, link = "geo:41.2,-72.3?z=12", "/#map=12/41.2/-72.3"
        if program == READ:
            return dict(map_visible=True, native_geo_uri=geo, native_long_link=link)
        assert arg is not None
        fields = [
            dict(selector=x, total=1, visible=1)
            for x in (
                "input[name=route_from]",
                "input[name=route_to]",
                "select.routing_engines",
            )
        ]
        return dict(
            geo=geo,
            long=link,
            classes="leaflet-container",
            busy=False,
            loading=self.fault == "loading",
            directionsContent=True if arg["directions"] else None,
            directionsFields=fields if arg["directions"] else None,
            ready=self.fault != "loading",
        )
