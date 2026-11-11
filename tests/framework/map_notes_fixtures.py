"""Explicit page/response fixtures for passive Notes evidence, no task admission."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from lab_generate_skill.sites.map.native_notes_capture import NativeNotesCapture
from map_artifact_fixtures import case
from map_route_fixtures import selected_spec, readout
from test_map_native_surface import SurfacePage
from test_slurm_commands import guard

ORIGIN = "http://127.0.0.1:1"


class NotesPage(SurfacePage):
    def __init__(self) -> None:
        super().__init__({"surface": {"map_visible": True}, "route": {}})
        self.listener: Any = None
        self.listener_fault = ""

    def on(self, event: str, callback: Any) -> None:
        assert event == "response"
        self.listener = callback
        if self.listener_fault == "attach":
            raise OSError("original partial Notes attach")

    def remove_listener(self, event: str, callback: Any) -> None:
        assert event == "response" and callback is self.listener
        self.listener = None
        if self.listener_fault == "detach":
            raise OSError("original Notes detach reply unknown")


class NotesResponse:
    def __init__(
        self, body: Any = b'{"type":"FeatureCollection","features":[]}'
    ) -> None:
        self.url = ORIGIN + "/api/0.6/notes.json?bbox=0,0,0.5,0.5"
        self.request = SimpleNamespace(method="GET", resource_type="xhr")
        self.status = 200
        self.headers = {"content-type": "application/json"}
        self.raw = body
        self.error: BaseException | None = None
        self.reads = 0

    def body(self) -> Any:
        self.reads += 1
        if self.error is not None:
            raise self.error
        return self.raw


def notes_case(root: Path) -> tuple[Any, ...]:
    writer, authority = case(root)
    writer.initialize(guard())
    c = NativeNotesCapture(writer.plan, writer, guard(30), ORIGIN)
    page = NotesPage()
    c.attach(page, guard())
    original = readout(selected_spec(writer, ORIGIN + "/"), 0)
    return c, page, original, writer, authority
