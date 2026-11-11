"""Explicit readiness through fixed resource/wire/collector; page/OS are doubles."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.map_browser_collection import MapBrowserPublication
from lab_generate_skill.adapters.browsergym.worker_client import BrowserWorkerFailure
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.sites.map.browser_initialization import (
    MapNativeBrowserInitializer,
)
from map_browser_collection_fixtures import CollectionCase
from map_browser_initialization_fixtures import selection, public_task
from test_map_browser_collection import capture
from test_browser_resource import enter, inspect
from test_slurm_commands import guard


def select_native(c: CollectionCase) -> None:
    task = public_task("http://127.0.0.1:8000/")
    config = c.configuration
    c.configuration = BrowserWorkerConfiguration.model_validate(
        config.model_copy(
            update={
                "spec": config.spec.model_copy(update={"task": task}),
                "initialization": selection("http://127.0.0.1:8000/"),
            }
        )
    )
    c.resource.spec = BrowserResourceSpec.model_validate(
        c.resource.spec.model_copy(update={"configuration": c.configuration})
    )


def test_original_ready_before_unique_return_and_closed_full_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = CollectionCase(tmp_path, monkeypatch)
    select_native(c)
    with enter(c.resource) as session:
        assert (
            c.engine is not None
            and c.collector is not None
            and c.collector.native is not None
        )
        init = c.engine.initializer
        assert (
            isinstance(init, MapNativeBrowserInitializer) and init.reference is not None
        )
        initial = c.engine.last_readout
        assert initial is not None and initial.observation.sequence == 0
        assert c.collector.native.requests.last_readout is initial
        assert c.calls.index("native-view") < c.calls.index("project")
        assert c.calls.count("navigate") == 1 and c.calls.count("project") == 1
        recorder, request = capture(c, session)
        recorder.capture(request, control=guard(30))
        assert recorder.result is not None
        publication = MapBrowserPublication.model_validate_json(
            recorder.result.private_result
        )
        assert publication.sequence == 0 and c.engine.last_readout is initial
    assert inspect(c.resource).state == "closed"
    c.participant = "controller"
    reader = MapArtifactReader(c.plan, Path(c.plan.workspace_root), c.authority())
    raw = reader.read(publication.handle, init.reference.path, guard())
    assert raw == init.last_fact
    fact = json.loads(raw)
    assert fact["stable_seconds"] >= 0.75 and fact["native_readiness"]["ready"] is True
    assert (
        not fact["new_observation_created"]
        and not fact["task_success_or_admission_claim"]
    )
    assert (
        reader.read(publication.handle, publication.terminal_readout.path, guard())
        == initial.model_dump_json().encode()
    )


def test_failed_readiness_has_no_public_return_and_retains_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = CollectionCase(tmp_path, monkeypatch)
    select_native(c)
    c.page_fault = "readiness"
    with pytest.raises(BrowserWorkerFailure) as caught:
        with enter(c.resource):
            pytest.fail("Readiness failure cannot yield initial observation")
    assert (
        caught.value.reply.error is not None
        and caught.value.reply.error.type_name == "OSError"
    )
    assert c.calls.count("navigate") == 1 and "project" not in c.calls
    assert c.engine is not None and c.engine.last_readout is None
    assert isinstance(c.engine.initializer, MapNativeBrowserInitializer)
    init = c.engine.initializer
    assert init.failure_ref is not None and init.reference is None
    assert (
        Path(c.plan.private_root) / "working" / init.failure_ref.path
    ).read_bytes() == init.failure_fact
    assert (
        inspect(c.resource).state == "closed"
        and c.collector is not None
        and c.collector.native is not None
    )
    assert c.collector.native.requests.relay.physical_closed
