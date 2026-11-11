"""Pinned original source inputs and explicit browser response doubles."""

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from lab_generate_skill.sites.map.native_served_rules import (
    RENDERER_READ,
    reviewed_sources,
)
from lab_generate_skill.sites.map.native_served_capture import NativeServedCapture
from map_artifact_fixtures import case
from map_route_fixtures import selected_spec, readout
from test_map_native_surface import SurfacePage
from test_slurm_commands import guard

INPUTS = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-intake-20261029-v1/frontend-fixture-inputs"
)
PINS = {
    "index.js": "10dd34fa707fa45b795c07c1070bd38c368e4c37e63825ca1b5ec93101e74424",
    "leaflet.share.js": "69e60af41fd672f84f919d72255465c46711cad2f1778b80cca8be3e50e7beba",
    "leaflet.layers.js": "54608669c8498eec2f834a92058ceb869f78b51b02249fd52161d00123b94228",
    "leaflet.osm.js": "19c69de257efcd54351f6344b8c3290fe9bbd2281312434a08f9a2d23d02f530",
}
ORIGIN = "http://127.0.0.1:1"
TILES = "http://127.0.0.1:2"


def originals() -> dict[str, bytes]:
    result = {}
    for name, pin in PINS.items():
        path = INPUTS / name
        assert path.resolve(strict=True) == path and not path.is_symlink()
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == pin
        result[name] = raw
    return result


class ServedPage(SurfacePage):
    def __init__(self) -> None:
        super().__init__({"surface": {"map_visible": True}, "route": {}})
        self.main_frame = object()
        self.listener: Any = None
        self.listener_fault = ""
        self.runtime: Any = dict(
            reviewed_sources(originals(), TILES).renderer_functions
        )
        self.renderer_reads = 0

    def on(self, event: str, callback: Any) -> None:
        assert event == "response"
        self.listener = callback
        if self.listener_fault == "attach":
            raise OSError("original partial listener attachment")

    def remove_listener(self, event: str, callback: Any) -> None:
        assert event == "response" and callback is self.listener
        self.listener = None
        if self.listener_fault == "detach":
            raise OSError("original detach reply lost")

    def evaluate(self, expression: str) -> Any:
        if expression == RENDERER_READ:
            self.renderer_reads += 1
            return self.runtime
        return super().evaluate(expression)


class Response:
    def __init__(self, page: ServedPage, name: str, body: bytes) -> None:
        self.url = ORIGIN + "/assets/" + name
        self.request = SimpleNamespace(resource_type="script", frame=page.main_frame)
        self.status = 200
        self.from_service_worker = False
        self.raw = body
        self.reads = 0
        self.error: BaseException | None = None

    def body(self) -> bytes:
        self.reads += 1
        if self.error is not None:
            raise self.error
        return self.raw


def served_case(root: Path) -> tuple[Any, ...]:
    writer, authority = case(root)
    writer.initialize(guard())
    collector = NativeServedCapture(
        writer.plan, writer, guard(30), ORIGIN, originals(), TILES
    )
    page = ServedPage()
    original = readout(selected_spec(writer, ORIGIN + "/"), 0)
    collector.attach(page, guard())
    responses = [
        Response(page, name, source.encode())
        for name, source in collector.expected.sources
    ]
    return collector, page, responses, original, writer, authority
