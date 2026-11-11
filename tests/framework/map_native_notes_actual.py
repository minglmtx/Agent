"""Actual Notes response and loss after native MapData/source/surface composition.

Controlled page only. No Notes business support or real Map site admission.
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
from lab_generate_skill.sites.map.native_served_capture import NativeServedCapture
from lab_generate_skill.sites.map.native_notes_capture import NativeNotesCapture
from browsergym_fixtures import operation, LoopbackAuthority, CHROMIUM
from map_artifact_fixtures import case
from map_route_fixtures import selected_spec
from map_native_route_actual import server_fixture
from map_native_served_actual import document_and_assets
from map_served_fixtures import originals, TILES
from test_slurm_commands import guard

NOTES_PATH = "/api/0.6/notes.json"
NOTES_BODY = b'{"type":"FeatureCollection","features":[]}'
NOTES_SCRIPT = """
window.triggerOriginalNotes = () => {
  jQuery.active += 1;
  const xhr = new XMLHttpRequest();
  xhr.open('GET', '/api/0.6/notes.json?bbox=0,0,0.5,0.5');
  xhr.onload = () => { window.notesBody = xhr.responseText; jQuery.active -= 1; };
  xhr.onerror = () => { window.notesReadFailed = true; jQuery.active -= 1; };
  xhr.send();
};
"""


def notes_document() -> tuple[bytes, dict[str, bytes]]:
    document, assets = document_and_assets(False)
    before = (
        b"document.getElementById('result').textContent = 'Native response received';"
    )
    assert document.count(before) == 1
    document = document.replace(before, before + b"window.triggerOriginalNotes();")
    document = document.replace(
        b"</html>", ("<script>" + NOTES_SCRIPT + "</script></html>").encode()
    )
    assets[NOTES_PATH] = NOTES_BODY
    return document, assets


def test_notes_actual_fixture_preflight() -> None:
    import playwright

    node = Path(playwright.__file__).parent / "driver/node"
    document, assets = notes_document()
    assert len(assets) == 5 and json.loads(assets[NOTES_PATH])["features"] == []
    for script in re.findall(rb"<script>(.*?)</script>", document, re.S):
        result = subprocess.run(
            [str(node), "--check"],
            input=script,
            capture_output=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode()
    for partial in (False, True):
        with server_fixture(
            "batch",
            document=document,
            assets=assets,
            incomplete_assets=frozenset([NOTES_PATH]) if partial else frozenset(),
        ) as fixture:
            assert (
                not fixture.native_calls
                and fixture.note_calls == 0
                and fixture.documents == 0
            )


@pytest.mark.parametrize("partial", [False, True])
def test_actual_notes_full_or_incomplete_preserves_original_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    partial: bool,
) -> None:
    from playwright.sync_api import Error

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(CHROMIUM).parents[2]))
    monkeypatch.setenv(
        "LD_LIBRARY_PATH",
        "/anvme/workspace/r102bf10-lab-generate-skill/assets/runtime-20261025-v1/cache/browser-libs:"
        + os.environ.get("LD_LIBRARY_PATH", ""),
    )
    document, assets = notes_document()
    writer, authority = case(tmp_path)
    writer.initialize(guard())
    with server_fixture(
        "batch",
        document=document,
        assets=assets,
        incomplete_assets=frozenset([NOTES_PATH]) if partial else frozenset(),
    ) as fixture:
        spec = selected_spec(writer, fixture.origin + "/")
        relay = NativeMapRelay(fixture.origin, writer, guard(180), max_requests=4)
        requests = MapNativeRequestCollector(writer.plan, relay)
        served = NativeServedCapture(
            writer.plan, writer, guard(180), fixture.origin, originals(), TILES
        )
        notes = NativeNotesCapture(writer.plan, writer, guard(180), fixture.origin)
        collector = MapNativeProcessCollector(requests, served=served, notes=notes)
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
            assert served.state == "verified" and notes.last_readout is initial
            button = re.search(
                r"\[([^\]]+)\] button [\'\"]Fetch Map Data[\'\"]",
                initial.observation.text or "",
            )
            assert button, initial.observation.text
            observed_error: Error | None = None
            try:
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
                engine.step(
                    BrowserAction(
                        action_id="finish",
                        protocol_id="browsergym-highlevel-v1",
                        name="send_msg_to_user",
                        payload="send_msg_to_user('done')",
                    ),
                    operation(spec, "finish"),
                    control=guard(30),
                )
            except Error as error:
                observed_error = error
            if partial:
                assert observed_error is not None and any(
                    observed_error is e for e in notes.errors
                )
                assert (
                    not notes.records[0]["complete"]
                    and notes.records[0]["capture_error"]
                )
            else:
                assert (
                    observed_error is None
                    and notes.records[0]["complete"]
                    and not notes.errors
                )
                collector.finish(guard(30))
                assert collector.final_captured
            assert (
                notes.last_readout
                is requests.last_readout
                is collector.surface.last_readout
                is engine.last_readout
            )
            assert [r.observation.sequence for r in requests.readouts] == list(
                range(len(requests.readouts))
            )
            assert (
                len(requests.readouts) in (2, 3)
                and len(fixture.native_calls) == 3
                and fixture.note_calls == 1
            )
            assert notes.next_index == 1 and len(notes.responses) == 1
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
                        "Original actual Notes test and cleanup", [primary, error]
                    )
                raise
        assert relay.physical_closed and engine.driver is None and collector.closed
    handle = writer.seal(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    closed = json.loads(reader.read(handle, "map-notes-close.json", guard()))
    assert closed["complete"] is (not partial) and closed["responses_seen"] == 1
    assert not closed["task_success_or_admission_claim"]
    saved = json.loads(reader.read(handle, "map-notes-0-end.json", guard()))
    if partial:
        assert saved["capture_error"] and "body" not in saved
    else:
        assert reader.read(handle, "map-notes-0.bin", guard()) == NOTES_BODY
