"""Actual Chromium plus complete surface/XHR chain on an explicit controlled page.

No original Map website, renderer/source provenance, DB or Actor claim.
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
from lab_generate_skill.sites.map.native_process_collector import (
    MapNativeProcessCollector,
)
from lab_generate_skill.sites.map.native_route_collector import (
    MapNativeRequestCollector,
)
from lab_generate_skill.sites.map.native_relay import NativeMapRelay
from lab_generate_skill.sites.map.native_surface_script import (
    COMBINED_READ,
    READ,
    NOTE_MARKERS_READ,
    ROUTE_READ,
)
from browsergym_fixtures import operation, LoopbackAuthority, CHROMIUM
from map_artifact_fixtures import case
from map_route_fixtures import selected_spec
from map_native_route_actual import SCRIPT, server_fixture
from test_slurm_commands import guard

SURFACE_SCRIPT = """
window.fixtureLayers = {'Map Data': false, 'Map Notes': false};
window.__labNativeLayerState = () => ({...window.fixtureLayers});
document.getElementById('native').addEventListener('click', () => {
  window.fixtureLayers['Map Data'] = true;
  document.getElementById('data').checked = true;
  document.getElementById('long_link').href = '/?layers=D';
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M1 1 L50 50 L80 10');
  path.setAttribute('stroke', '#000000');
  document.querySelector('svg').appendChild(path);
});
"""
DOCUMENT = ("""<html><title>Controlled route and MapData</title>
<div id="map"><button id="native">Fetch Map Data</button><p id="result">No request yet</p>
<div class="layers-ui"><div class="overlay-layers">
<label><input id="data" type="checkbox">Map Data</label>
<label><input type="checkbox">Map Notes</label></div></div>
<input name="route_from" value="Central Park"><input name="route_to" value="Times Square">
<select class="routing_engines"><option selected>Car (OSRM)</option></select>
<a id="long_link" href="/?layers=">Link</a>
<div id="sidebar_content"><table><tr class="turn"><td>Original retained turn</td></tr></table></div>
<div class="leaflet-overlay-pane"><svg width="200" height="100">
<path stroke="#03f" d="M0 0 L10 10 L20 20 L30 30 L40 40"></path></svg></div></div>
<script>""" + SCRIPT + SURFACE_SCRIPT + "</script></html>").encode()


def test_surface_browser_fixture_preflight() -> None:
    import playwright

    node = Path(playwright.__file__).parent / "driver/node"
    result = subprocess.run(
        [str(node), "--check"],
        input=(SCRIPT + SURFACE_SCRIPT).encode(),
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    with server_fixture("batch", document=DOCUMENT) as fixture:
        assert fixture.documents == 0 and not fixture.native_calls


@pytest.mark.parametrize("ending", ["protocol", "limit"])
def test_actual_unique_return_surface_and_native_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ending: str,
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    with server_fixture("batch", document=DOCUMENT) as fixture:
        spec = selected_spec(writer, fixture.origin + "/")
        relay = NativeMapRelay(fixture.origin, writer, guard(180), max_requests=4)
        requests = MapNativeRequestCollector(writer.plan, relay)
        collector = MapNativeProcessCollector(requests)
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
            initial = engine.start(original, control=guard(90))
            assert collector.surface.last_readout is requests.last_readout is initial
            button = re.search(
                r"\[([^\]]+)\] button [\'\"]Fetch Map Data[\'\"]",
                initial.observation.text or "",
            )
            assert button, initial.observation.text
            clicked = engine.step(
                BrowserAction(
                    action_id="native",
                    protocol_id="browsergym-highlevel-v1",
                    name="click",
                    payload=f"click({button.group(1)!r})",
                ),
                operation(spec, "click"),
                control=guard(30),
            )
            if ending == "protocol":
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
            else:
                final = clicked
            collector.finish(guard(30))
            assert (
                collector.surface.last_readout
                is requests.last_readout
                is engine.last_readout
                is final
            )
            assert len(requests.readouts) == (3 if ending == "protocol" else 2)
            assert len(fixture.native_calls) == 3 and collector.final_captured
            assert engine.env.page.evaluate("window.actualXHRs") == 1
            # Pure readers agree on the same idle controlled DOM. These extra
            # fixture reads are not observations and are not production capture.
            page = engine.env.page
            combined = page.evaluate(COMBINED_READ)
            assert combined == {
                "surface": {**page.evaluate(READ), **page.evaluate(NOTE_MARKERS_READ)},
                "route": page.evaluate(ROUTE_READ),
            }
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
                        "Original combined surface test and cleanup", [primary, error]
                    )
                raise
        assert relay.physical_closed and engine.driver is None and collector.closed
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    first = json.loads(reader.read(handle, "map-page-0-unique_return.json", guard()))
    terminal_name = (
        "map-page-2-terminal.json"
        if ending == "protocol"
        else "map-page-1-terminal.json"
    )
    last = json.loads(reader.read(handle, terminal_name, guard()))
    before, after = first["facts"], last["facts"]
    assert before["route"] == after["route"]
    assert before["route"]["route_visible"] and before["route"]["rows"] == [
        "Original retained turn"
    ]
    assert before["surface"]["native_active_overlays"] == {
        "Map Data": False,
        "Map Notes": False,
    }
    assert after["surface"]["native_active_overlays"] == {
        "Map Data": True,
        "Map Notes": False,
    }
    assert len(before["surface"]["rendered_paths"]) == 1
    assert len(after["surface"]["rendered_paths"]) == 2
    assert after["surface"]["rendered_paths"][1]["stroke"] == "#000000"
    assert last["original_readout"] == final.model_dump(mode="json")
    assert last["facts"] == combined and last["new_action_or_observation"] is False
