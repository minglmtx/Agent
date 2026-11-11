"""Real original relay/files, explicit synthetic HTTP responses and Page callbacks."""

from dataclasses import replace
import hashlib
import json
from typing import Any
from urllib.request import build_opener, ProxyHandler
import pytest
from lab_generate_skill.domain.map_private_artifact import (
    MapArtifactHandle,
    MapArtifactManifest,
)
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.native_http import NativeMapHttpClient, NativeResponse
from lab_generate_skill.sites.map.native_bounds import Bounds, serialized_xml_bounds
from lab_generate_skill.sites.map.terminal_evidence import TerminalMapEvidence
from lab_generate_skill.sites.map.terminal_files import TerminalFiles
from map_route_fixtures import Route
from map_initial_records_fixtures import InitialCase
from map_terminal_fixtures import TerminalCase
from test_slurm_commands import guard

REGION = (
    "-74.01369094848634",
    "40.74784218528665",
    "-73.95532608032228",
    "40.79106937427438",
)
CAP = b"You requested too many nodes (limit is 50000). Either request a smaller area, or use planet.osm\n"


class Requests:
    def __init__(self, patch: pytest.MonkeyPatch, mode: str) -> None:
        self.patch = patch
        self.mode = mode
        self.calls: list[Bounds] = []
        self.delivered: bytes | None = None
        self.bounds = (
            REGION if mode != "narrow" else ("-74.01", "40.75", "-73.96", "40.79")
        )

        def fetch(
            client: NativeMapHttpClient, bounds: Bounds, deadline: float
        ) -> NativeResponse:
            self.calls.append(bounds)
            if mode == "non200":
                return NativeResponse(503, "text/plain", b"original unavailable")
            if mode == "batch" and bounds == self.bounds:
                return NativeResponse(400, "text/plain", CAP)
            w, s, e, n = serialized_xml_bounds(bounds)
            # Complete empty native XML is transport evidence, not task success.
            body = f'<osm version="0.6" generator="fixture"><bounds minlon="{w}" minlat="{s}" maxlon="{e}" maxlat="{n}"/></osm>'.encode()
            return NativeResponse(200, "application/xml", body)

        patch.setattr(NativeMapHttpClient, "fetch", fetch)

    def __call__(self, case: InitialCase) -> None:
        b = case.browser
        assert b.collector is not None and b.collector.native is not None

        # The initial-only Page double requires `arg`; Playwright's terminal
        # renderer wait does not. Model only this original no-argument call.
        def settled(expression: str, *, timeout: float) -> None:
            assert expression == "() => !window.jQuery || jQuery.active === 0"
            assert timeout > 0
            b.calls.append("original-native-renderer-settled")

        self.patch.setattr(b.page, "wait_for_function", settled)
        requests = b.collector.native.requests
        route = Route(requests.relay.origin, query="bbox=" + ",".join(self.bounds))
        requests._receive(route)
        assert route.aborts == 0 and len(route.calls) == 1
        opener = build_opener(ProxyHandler({}))
        from urllib.error import HTTPError

        try:
            response = opener.open(route.calls[0]["url"], timeout=10)
        except HTTPError as error:
            response = error
        with response:
            self.delivered = response.read()


class DerivedFiles:
    """Read-only test mutation of already read original bytes, not production authority."""

    def __init__(self, source: TerminalMapEvidence) -> None:
        self.original = source.files.manifest
        self.data = {
            name: source.files.read(name, guard(30)) for name in source.files.members
        }

    def manifest(
        self, handle: MapArtifactHandle, control: OperationControl
    ) -> MapArtifactManifest:
        control.checkpoint()
        entries = tuple(
            ReleaseFile(
                path=name,
                size_bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                executable=False,
            )
            for name, raw in sorted(self.data.items())
        )
        return self.original.model_copy(
            update={
                "artifact": self.original.artifact.model_copy(update={"files": entries})
            }
        )

    def read(
        self, handle: MapArtifactHandle, name: str, control: OperationControl
    ) -> bytes:
        control.checkpoint()
        return self.data[name]

    def change(self, name: str, **values: Any) -> None:
        record = json.loads(self.data[name])
        record.update(values)
        self.data[name] = json.dumps(
            record, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()

    def evidence(self, source: TerminalMapEvidence) -> TerminalMapEvidence:
        return replace(source, files=TerminalFiles(source.publication, self, guard()))


def read_original(c: TerminalCase) -> tuple[TerminalMapEvidence, DerivedFiles]:
    value = c.load()
    c.initial.browser.participant = "controller"
    try:
        return value, DerivedFiles(value)
    finally:
        c.initial.browser.participant = "worker"
