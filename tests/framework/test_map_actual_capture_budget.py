"""Actual capture port uses original native budget and retains original readout."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Literal
import pytest
from lab_generate_skill.domain.browser_capture import BrowserCaptureIntent
from lab_generate_skill.sites.map.page_capture import PAGE_HEALTH_PROGRAM
from map_browser_capture_native import capture
from map_browser_collection_fixtures import CollectionCase
from map_terminal_fixtures import CONTRACT, terminal
from map_registered_worker_fixtures import RegisteredMapCase
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_browser_process import action
from test_browser_resource import enter, inspect
from test_map_page_health import health
from test_slurm_commands import guard


@pytest.mark.parametrize("collector", ["map-native-process", "map-page-health"])
def test_actual_capture_budget_matches_original_contract_without_new_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collector: Literal["map-native-process", "map-page-health"],
    registered_map: RegisteredMapCase,
) -> None:
    raw = CONTRACT.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "50356bbd0811eaac447f9bbef29a348a552dc38c2478a1cbec13464f1719cb2d"
    )
    native_seconds = json.loads(raw)["map_native_layer"]["native_batch_seconds"]
    if collector == "map-page-health":
        _health_after_original_publication(registered_map, monkeypatch)
        return
    c = CollectionCase(tmp_path, monkeypatch)
    with enter(c.resource) as session:
        original_action = action().model_copy(
            update={"name": "send_msg_to_user", "payload": "send_msg_to_user('done')"}
        )
        session.step(
            original_action,
            c.resource.op.model_copy(
                update={"operation_id": "original-terminal-action"}
            ),
            control=guard(),
        )
        assert c.engine is not None and c.collector is not None
        native = c.collector.native
        assert native is not None and native.requests.state == "terminal_pending"
        original = c.engine.last_readout
        observed_ref = session.observation_ref
        evaluate = c.page.evaluate

        def page_read(expression: str, args: Any = None) -> Any:
            if expression == PAGE_HEALTH_PROGRAM:
                return health(c.page.url)
            return evaluate(expression, args)

        monkeypatch.setattr(c.page, "evaluate", page_read)
        began = datetime.now(timezone.utc)
        pair = capture(c.resource, session, collector)
        ended = datetime.now(timezone.utc)
        intent = BrowserCaptureIntent.model_validate_json(
            c.resource.evidence.read(pair.intent_ref, control=guard())
        )
        seconds = native_seconds if collector == "map-native-process" else 180
        deadline = intent.request.operation.deadline
        assert (
            began + timedelta(seconds=seconds)
            <= deadline
            <= ended + timedelta(seconds=seconds)
        )
        assert (
            c.engine.last_readout is original
            and session.observation_ref == observed_ref
        )
        assert (
            len(native.requests.readouts) == 2 and c.calls.count("actual-action") == 1
        )
        if collector == "map-native-process":
            assert native.requests.finish_record is not None
            assert native.requests.finish_record["original_deadlines_extended"] is False
            assert c.collector.publication is not None
        else:
            assert (
                native.requests.finish_record is None
                and c.collector.publication is None
            )
    assert inspect(c.resource).state == "closed"


def _health_after_original_publication(
    registered: RegisteredMapCase, patch: pytest.MonkeyPatch
) -> None:
    # Health belongs to MapBrowserCapture and requires the original publication.
    # Use the existing prepared graph; a generic public-start collector cannot
    # serve this request and must keep rejecting it.
    with terminal(registered, patch, action="protocol") as case:
        b = case.initial.browser
        assert b.engine is not None and b.collector is not None
        native = b.collector.native
        assert native is not None and native.requests.finish_record is not None
        published = b.collector.publication
        original = b.engine.last_readout
        observed = case.initial.session.observation_ref
        calls = list(b.calls)
        finish = dict(native.requests.finish_record)
        evaluate = b.page.evaluate

        def page_read(expression: str, args: Any = None) -> Any:
            return (
                health(b.page.url)
                if expression == PAGE_HEALTH_PROGRAM
                else evaluate(expression, args)
            )

        patch.setattr(b.page, "evaluate", page_read)
        began = datetime.now(timezone.utc)
        pair = capture(b.resource, case.initial.session, "map-page-health")
        ended = datetime.now(timezone.utc)
        intent = BrowserCaptureIntent.model_validate_json(
            b.resource.evidence.read(pair.intent_ref, control=guard())
        )
        assert (
            began + timedelta(seconds=180)
            <= intent.request.operation.deadline
            <= ended + timedelta(seconds=180)
        )
        assert (
            b.engine.last_readout is original
            and case.initial.session.observation_ref == observed
        )
        assert b.collector.publication is published and published is not None
        assert (
            native.requests.finish_record == finish
            and len(native.requests.readouts) == 2
        )
        assert b.calls == calls and b.calls.count("actual-action") == 1
