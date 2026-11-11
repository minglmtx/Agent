"""Original fixed worker -> unique return -> terminal file capture -> original closure."""

from datetime import timedelta
import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
    BrowserWorkerFailure,
)
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.adapters.map_artifacts.browser_files import (
    OriginalMapBrowserFiles,
)
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.map_browser_collection import (
    MapBrowserCollectionSpec,
    MapBrowserPublication,
)
from lab_generate_skill.domain.map_browser_inputs import MapBrowserInputs
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from map_browser_collection_fixtures import CollectionCase
from test_browser_resource import enter, inspect
from test_browser_capture import Authority
from test_browser_process import action
from test_slurm_commands import guard


def capture(
    c: CollectionCase, session: EvidenceBrowserSession
) -> tuple[RecordedBrowserCapture, BrowserCaptureRequest]:
    client = session.engine
    assert (
        isinstance(client, SupervisedBrowserSession) and client.last_readout is not None
    )
    req = BrowserCaptureRequest(
        scope=client.spec.scope,
        operation=c.resource.op.model_copy(
            update={"operation_id": "original-terminal-capture"}
        ),
        observation_sha256=hashlib.sha256(
            client.last_readout.observation.model_dump_json().encode()
        ).hexdigest(),
        collector_id="map-native-process",
        collector_version="1",
    )
    return (
        RecordedBrowserCapture(
            client, c.resource.evidence, Authority(c.resource.evidence)
        ),
        req,
    )


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CollectionCase:
    return CollectionCase(tmp_path, monkeypatch)


@pytest.mark.parametrize("terminal", [False, True])
def test_fixed_worker_navigation_action_capture_and_complete_original_readback(
    c: CollectionCase, terminal: bool
) -> None:
    with enter(c.resource) as session:
        assert (
            c.engine is not None
            and c.collector is not None
            and c.collector.native is not None
        )
        native = c.collector.native
        assert c.calls.index("route-before-navigation") < c.calls.index("navigate")
        first = c.engine.last_readout
        assert first is not None and native.requests.last_readout is first
        assert native.served is not None and native.served.state == "verified"
        original_action = action()
        if terminal:
            original_action = original_action.model_copy(
                update={
                    "name": "send_msg_to_user",
                    "payload": "send_msg_to_user('done')",
                }
            )
        session.step(
            original_action,
            c.resource.op.model_copy(update={"operation_id": "actual-action"}),
            control=guard(),
        )
        last = c.engine.last_readout
        assert last is not None and last.observation.sequence == 1
        assert last.protocol_terminal is terminal
        assert native.requests.state == ("terminal_pending" if terminal else "active")
        assert native.requests.finish_record is None and not native.final_captured
        recorder, req = capture(c, session)
        reference = recorder.capture(req, control=guard(30))
        assert recorder.result is not None
        publication = MapBrowserPublication.model_validate_json(
            recorder.result.private_result
        )
        assert reference.visibility == "private" and publication.sequence == 1
        assert c.engine.last_readout is last and native.requests.last_readout is last
        assert (
            native.requests.relay.physical_closed and c.collector.state == "published"
        )
        assert c.calls.count("navigate") == 1 and c.calls.count("actual-action") == 1
        with pytest.raises(InvalidTransition):
            c.collector.before_action(guard())
        with pytest.raises(InvalidTransition):
            c.collector.collect(c.page, "map-native-process", "1", guard())
        before = len(c.resource.channels[0].calls)
        with pytest.raises(InvalidTransition):
            recorder.capture(req, control=guard())
        assert len(c.resource.channels[0].calls) == before
    assert inspect(c.resource).state == "closed" and c.calls.count("driver") == 1
    c.participant = "controller"
    reader = MapArtifactReader(c.plan, Path(c.plan.workspace_root), c.authority())
    manifest = reader.manifest(publication.handle, guard())
    assert len(manifest.artifact.files) > 10
    assert (
        reader.read(publication.handle, publication.terminal_readout.path, guard())
        == last.model_dump_json().encode()
    )
    facts = json.loads(
        reader.read(publication.handle, "map-page-1-terminal.json", guard())
    )
    assert facts["new_action_or_observation"] is False and facts[
        "original_readout"
    ] == last.model_dump(mode="json")
    ended = json.loads(
        reader.read(publication.handle, "map-process-close.json", guard())
    )
    assert (
        ended["original_relay_physical_closed"] is True and ended["request_count"] == 0
    )
    assert c.collector.state == "closed"


@pytest.mark.parametrize("fault", ["attach", "surface", "source", "operation"])
def test_failed_original_start_retains_partial_and_never_navigates_again(
    c: CollectionCase, fault: str
) -> None:
    c.page_fault = fault
    if fault == "source":
        assert c.configuration.map_inputs is not None
        pin = c.configuration.map_inputs.collection.original_sources.files[0]
        path = (
            Path(c.configuration.map_inputs.collection.original_sources.root) / pin.path
        )
        path.chmod(0o600)
        path.write_bytes(b"changed original source")
    elif fault == "operation":
        assert c.configuration.map_inputs is not None
        inputs = c.configuration.map_inputs
        inputs = inputs.model_copy(
            update={
                "collection": inputs.collection.model_copy(
                    update={
                        "operation": inputs.collection.operation.model_copy(
                            update={"operation_id": "changed-original"}
                        )
                    }
                )
            }
        )
        c.configuration = BrowserWorkerConfiguration.model_validate(
            c.configuration.model_copy(update={"map_inputs": inputs})
        )
        c.resource.spec = BrowserResourceSpec.model_validate(
            c.resource.spec.model_copy(update={"configuration": c.configuration})
        )
    with pytest.raises(BrowserWorkerFailure) as caught:
        with enter(c.resource):
            pytest.fail("Failed original startup cannot yield browser")
    assert caught.value.reply.error is not None
    assert (
        caught.value.reply.error.type_name
        == {
            "source": "EvidenceIntegrityError",
            "operation": "OwnershipConflict",
            "attach": "OSError",
            "surface": "OSError",
        }[fault]
    )
    assert c.calls.count("navigate") == int(fault == "surface")
    assert c.engine is not None and c.collector is not None
    assert c.collector.publication is None and inspect(c.resource).state == "closed"
    if c.collector.native is not None:
        assert c.collector.native.requests.relay.physical_closed
    if fault in ("source", "operation"):
        assert not Path(c.plan.private_root).exists()
    else:
        assert (
            Path(c.plan.private_root) / "working/map-collection-intent.json"
        ).exists()


def test_seal_lost_ack_keeps_handle_and_never_repeats_native_capture(
    c: CollectionCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    with enter(c.resource) as session:
        assert c.collector is not None and isinstance(
            c.collector.files, OriginalMapBrowserFiles
        )
        files = c.collector.files
        original = files.seal
        calls: list[str] = []

        def lose(control: Any) -> Any:
            calls.append("seal")
            original(control)
            raise OSError("original seal acknowledgement lost")

        monkeypatch.setattr(files, "seal", lose)
        recorder, req = capture(c, session)
        with pytest.raises(BrowserWorkerFailure):
            recorder.capture(req, control=guard(30))
        assert calls == ["seal"] and files.writer.handle is not None
        assert c.collector.publication is None and c.collector.native is not None
        assert c.collector.native.requests.relay.physical_closed
        with pytest.raises(InvalidTransition):
            recorder.capture(req, control=guard())
    assert calls == ["seal"] and inspect(c.resource).state == "closed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("tile_origin", ""),
        ("tile_origin", None),
        ("tile_origin", "http://localhost:80"),
        ("tile_origin", "http://127.0.0.1:80/path"),
        ("max_requests", 0),
        ("max_requests", 257),
        ("max_requests", True),
        ("max_requests", "3"),
    ],
    ids=["empty", "null", "host", "path", "zero", "over", "bool", "wrong-type"],
)
def test_collection_rejects_illegal_configuration(
    c: CollectionCase, field: str, value: Any
) -> None:
    assert c.configuration.map_inputs is not None
    data = c.configuration.map_inputs.collection.model_dump(mode="json")
    data[field] = value
    with pytest.raises(ValidationError):
        MapBrowserCollectionSpec.model_validate_json(json.dumps(data))


def test_original_source_scope_and_old_inputs_rejected(c: CollectionCase) -> None:
    assert c.configuration.map_inputs is not None
    inputs = c.configuration.map_inputs
    for patch in (
        {"schema_version": "map-browser-inputs/1"},
        {
            "collection": inputs.collection.model_copy(
                update={
                    "original_sources": inputs.collection.original_sources.model_copy(
                        update={"root": inputs.evidence_root}
                    )
                }
            )
        },
        {
            "collection": inputs.collection.model_copy(
                update={
                    "operation": c.resource.op.model_copy(
                        update={"allocation_id": "foreign"}
                    )
                }
            )
        },
    ):
        with pytest.raises(ValidationError):
            MapBrowserInputs.model_validate(inputs.model_copy(update=patch))
    for count in (0, 3):
        with pytest.raises(ValidationError):
            MapBrowserCollectionSpec.model_validate(
                inputs.collection.model_copy(
                    update={
                        "original_sources": inputs.collection.original_sources.model_copy(
                            update={
                                "files": inputs.collection.original_sources.files[
                                    :count
                                ]
                            }
                        )
                    }
                )
            )


def test_lifetime_cannot_be_renewed_by_later_action_or_wall_clock(
    c: CollectionCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.adapters.browsergym.collection_control import (
        OriginalMapCollectionControl,
    )
    from lab_generate_skill.adapters.clock import SystemClock
    from lab_generate_skill.domain.errors import OperationStopped

    lifetime = OriginalMapCollectionControl(c.resource.op, SystemClock())
    initial = lifetime.checkpoint()
    assert lifetime.intersect(guard(86400)).checkpoint() <= initial
    monkeypatch.setattr(
        lifetime.bound, "_expires", -1.0
    )  # Exhaust original monotonic deadline.
    with pytest.raises(OperationStopped):
        lifetime.intersect(guard(86400)).checkpoint()
    expired = c.resource.op.model_copy(
        update={"deadline": SystemClock().utcnow() - timedelta(seconds=1)}
    )
    with pytest.raises(ValueError):
        OriginalMapCollectionControl(expired, SystemClock())


def test_unknown_capture_selector_and_close_do_not_finish_or_seal(
    c: CollectionCase,
) -> None:
    with enter(c.resource):
        assert c.collector is not None and c.collector.native is not None
        native = c.collector.native
        reads = c.page.reads
        for selector, version in (
            ("", "1"),
            ("map-native-process", "2"),
            ("admin-page-health", "1"),
        ):
            with pytest.raises(OwnershipConflict):
                c.collector.collect(c.page, selector, version, guard())
        assert c.collector.state == "active" and c.page.reads == reads
    assert native.requests.finish_record is None and c.collector.publication is None
    assert native.requests.relay.physical_closed
    assert not (Path(c.plan.private_root) / "published/manifest.json").exists()
    assert c.calls.count("unroute") == 1
    c.collector.close(guard())
    assert c.calls.count("unroute") == 1


def test_fixed_map_dispatch_requires_live_guard_before_native_effect(
    c: CollectionCase,
) -> None:
    from lab_generate_skill.bootstrap.browser_engine import build_browser_engine
    from lab_generate_skill.adapters.clock import SystemClock
    from browsergym_fixtures import LoopbackAuthority

    with pytest.raises(ValueError, match="live worker guard"):
        build_browser_engine(
            c.configuration, LoopbackAuthority(), SystemClock(), worker_guard=None
        )
    assert not Path(c.plan.private_root).exists() and c.page is None
