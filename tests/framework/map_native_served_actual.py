"""Actual script responses/runtime functions plus original process composition.

Controlled page, with a minimal Leaflet class scaffold and unexecuted index
ready callback: this tests source proof, not real Map frontend/service behavior.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import pytest
from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.map.native_process_collector import (
    MapNativeProcessCollector,
)
from lab_generate_skill.sites.map.native_route_collector import (
    MapNativeRequestCollector,
)
from lab_generate_skill.sites.map.native_relay import NativeMapRelay
from lab_generate_skill.sites.map.native_served_capture import NativeServedCapture
from lab_generate_skill.sites.map.native_served_rules import (
    reviewed_sources,
    RENDERER_READ,
)
from browsergym_fixtures import operation, LoopbackAuthority, CHROMIUM
from map_artifact_fixtures import case
from map_route_fixtures import selected_spec
from map_native_route_actual import server_fixture
from map_native_surface_actual import DOCUMENT
from map_served_fixtures import originals, TILES
from test_slurm_commands import guard

BOOT = """
window.L = {};
function FixtureClass() {}
FixtureClass.extend = function(properties) {
  function DefinedClass() {}
  DefinedClass.prototype = properties;
  DefinedClass.extend = FixtureClass.extend;
  return DefinedClass;
};
L.TileLayer = FixtureClass;
L.FeatureGroup = FixtureClass;
window.$ = function() { return {ready: function(callback) { window.fixtureNativeReady = callback; }}; };
"""


def document_and_assets(tamper: bool) -> tuple[bytes, dict[str, bytes]]:
    expected = reviewed_sources(originals(), TILES)
    assets = {"/assets/" + name: source.encode() for name, source in expected.sources}
    tags = "".join(
        '<script src="/assets/' + name + '"></script>'
        for name in (
            "leaflet.osm.js",
            "leaflet.share.js",
            "leaflet.layers.js",
            "index.js",
        )
    )
    injection = "<script>" + BOOT + "</script>" + tags
    document = DOCUMENT.replace(b"<script>", injection.encode() + b"<script>", 1)
    if tamper:
        document = document.replace(
            b"</html>",
            b"<script>L.OSM.DataLayer.prototype.interestingNode = function () {return false;};</script></html>",
        )
    return document, assets


def test_served_actual_fixture_preflight() -> None:
    import playwright

    node = Path(playwright.__file__).parent / "driver/node"
    for tamper in (False, True):
        document, assets = document_and_assets(tamper)
        scripts = re.findall(rb"<script>(.*?)</script>", document, re.S)
        assert scripts and len(assets) == 4
        for script in [
            *scripts,
            *assets.values(),
            ("const reader = " + RENDERER_READ + ";").encode(),
        ]:
            result = subprocess.run(
                [str(node), "--check"],
                input=script,
                capture_output=True,
                timeout=15,
                check=False,
            )
            assert result.returncode == 0, result.stderr.decode()
        with server_fixture("batch", document=document, assets=assets) as fixture:
            assert fixture.documents == 0 and not fixture.native_calls


@pytest.mark.parametrize("tamper", [False, True])
def test_actual_served_sources_surface_and_native_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: bool,
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    document, assets = document_and_assets(tamper)
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    with server_fixture("batch", document=document, assets=assets) as fixture:
        spec = selected_spec(writer, fixture.origin + "/")
        relay = NativeMapRelay(fixture.origin, writer, guard(180), max_requests=4)
        requests = MapNativeRequestCollector(writer.plan, relay)
        served = NativeServedCapture(
            writer.plan, writer, guard(180), fixture.origin, originals(), TILES
        )
        collector = MapNativeProcessCollector(requests, served=served)
        engine = BrowserGymEngine(
            spec,
            LoopbackAuthority(),
            SystemClock(),
            NavigatePublicTask(),
            process_collector=collector,
        )
        original = operation(spec, "start")
        primary: BaseException | None = None
        try:
            if tamper:
                with pytest.raises(
                    EvidenceIntegrityError, match="renderer functions differ"
                ):
                    engine.start(original, control=guard(90))
                assert (
                    engine.last_readout
                    is requests.last_readout
                    is collector.surface.last_readout
                )
                assert engine.last_readout is not None and len(requests.readouts) == 1
                assert served.state == "failed" and not fixture.native_calls
            else:
                initial = engine.start(original, control=guard(90))
                assert (
                    served.state == "verified"
                    and served.summary is not None
                    and served.summary["passed"]
                )
                button = re.search(
                    r"\[([^\]]+)\] button [\'\"]Fetch Map Data[\'\"]",
                    initial.observation.text or "",
                )
                assert button, initial.observation.text
                engine.step(
                    BrowserAction(
                        action_id="native",
                        protocol_id="browsergym-highlevel-v1",
                        name="click",
                        payload=f"click({button.group(1)!r})",
                    ),
                    operation(spec, "click"),
                    control=guard(30),
                )
                final = engine.step(
                    BrowserAction(
                        action_id="finish",
                        protocol_id="browsergym-highlevel-v1",
                        name="send_msg_to_user",
                        payload="send_msg_to_user('done')",
                    ),
                    operation(spec, "finish"),
                    control=guard(30),
                )
                assert (
                    requests.last_readout
                    is collector.surface.last_readout
                    is engine.last_readout
                    is final
                )
                collector.finish(guard(30))
                assert len(requests.readouts) == 3 and len(fixture.native_calls) == 3
                assert engine.env.page.evaluate("window.actualXHRs") == 1
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                engine.close(
                    original.cleanup(
                        "close", now=datetime.now(timezone.utc), seconds=30
                    ),
                    control=guard(30),
                )
            except BaseException as error:
                if primary is not None:
                    raise BaseExceptionGroup(
                        "Original served browser test and close", [primary, error]
                    )
                raise
        assert relay.physical_closed and engine.driver is None and collector.closed
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    summary = json.loads(reader.read(handle, "map-actually-served.json", guard()))
    assert summary["passed"] is (not tamper) and len(summary["responses"]) == 4
    assert len(summary["matched_sources"]) == 4
    for row in summary["responses"]:
        assert row["original_main_frame"] and row["from_service_worker"] is False
        assert (
            reader.read(handle, row["body"]["path"], guard())
            == assets[re.sub(r"^http://[^/]+", "", row["actual_url"])]
        )
    if tamper:
        assert "renderer functions differ" in summary["error"]
    else:
        final_page = json.loads(
            reader.read(handle, "map-page-2-unique_return.json", guard())
        )
        assert len(final_page["facts"]["surface"]["rendered_paths"]) == 2
        assert final_page["facts"]["route"]["route_visible"]
