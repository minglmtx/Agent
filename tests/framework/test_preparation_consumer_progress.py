"""Original preparation reference identity and local stage diagnostics only."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.ledger.resource_facts import ResourceFacts
from lab_generate_skill.adapters.sites.task_preparation_state import (
    TaskPreparationState,
)
import lab_generate_skill.adapters.sites.task_preparation_state as progress
from task_resource_owner_fixtures import owned_task
from site_instance_fixtures import node_path as node_path

E = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-navigation42-production-20261102-v1"
)


def test_retained_real_site_spec_same_bytes_different_producer_is_not_same_reference() -> (
    None
):
    # Exact already-confirmed current facts, never a scan/replay or new grant.
    blobs = E / "production-4904699/evidence/blobs"
    plan = json.loads(
        (
            blobs / "8f264141d58c2342ba90e00f8c72a95995e9891d230188ef26a7afe2d6c21e78"
        ).read_bytes()
    )
    declaration = json.loads((blobs / plan["declaration_ref"]["sha256"]).read_bytes())
    intent = json.loads(
        (
            blobs / "f1b6fcec820064f52e6210c8a5b95479594223f30b528411343eaebf0be0559f"
        ).read_bytes()
    )
    original = intent["configuration_ref"]
    expected = ResourceFacts("site").reference(
        (blobs / original["sha256"]).read_bytes(), "site-resource-spec/1"
    )
    assert expected.model_dump(mode="json") == original
    assert original["sha256"] == declaration["site_spec_ref"]["sha256"]
    assert original != declaration["site_spec_ref"]
    assert original["producer"] == "fixed-site-resource"
    assert (
        declaration["site_spec_ref"]["producer"]
        == "map-navigation-production-inputs-v1"
    )


def test_local_stage_events_are_nested_and_do_not_change_business_state(
    capsys: pytest.CaptureFixture[str],
) -> None:
    s = TaskPreparationState()
    with s.stage("acquire.site-open"):
        with s.stage("held.resource-facts"):
            pass
    assert [(label, event) for label, event, _ in s.stage_timings] == [
        ("acquire.site-open", "begin"),
        ("held.resource-facts", "begin"),
        ("held.resource-facts", "end"),
        ("acquire.site-open", "end"),
    ]
    times = [t for _, _, t in s.stage_timings]
    assert times == sorted(times)
    assert s.phase == "new" and not s.references
    assert capsys.readouterr().err.count("TASK_PREPARATION_STAGE") == 4


@pytest.mark.parametrize("fault", ["stderr", "clock"])
def test_diagnostic_failure_preserves_original_failure(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    failure = RuntimeError("original preparation failure")

    def fail(*a: Any, **k: Any) -> Any:
        raise OSError("unit diagnostic unavailable")

    if fault == "stderr":
        monkeypatch.setattr(
            progress,
            "sys",
            SimpleNamespace(stderr=SimpleNamespace(write=fail, flush=fail)),
        )
    else:
        monkeypatch.setattr(progress, "time", SimpleNamespace(monotonic=fail))
    state = TaskPreparationState()
    with pytest.raises(RuntimeError) as caught:
        with state.stage("acquire.site-open"):
            raise failure
    assert caught.value is failure
    assert state.phase == "new" and not state.references


def test_original_owned_consumer_records_acquire_held_native_and_close(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Existing fake native/model/kernel premises, never a production permission.
    with owned_task(node_path, monkeypatch) as (c, r):
        result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert result.evaluation.status == "success"
        events = c.bundle.preparation.state.stage_timings
        assert {
            "acquire.declarations",
            "acquire.source-authority",
            "acquire.site-open",
            "acquire.held",
            "held.source-authority",
            "native.execute",
        } <= {name for name, _, _ in events}
        assert not any(event == "failed" for _, event, _ in events)


@pytest.mark.parametrize("fault", ["stderr", "clock"])
def test_original_consumer_markers_never_mask_primary_or_change_permission(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    import lab_generate_skill.adapters.operation_progress as markers

    failure = RuntimeError("original long consumer failed")

    def fail(*a: Any, **k: Any) -> Any:
        raise OSError("diagnostic sink unavailable")

    if fault == "stderr":
        monkeypatch.setattr(
            markers,
            "sys",
            SimpleNamespace(stderr=SimpleNamespace(write=fail, flush=fail)),
        )
    else:
        monkeypatch.setattr(markers, "time", SimpleNamespace(monotonic=fail))
    with pytest.raises(RuntimeError) as caught:
        with markers.operation_stage("source.current-claim"):
            raise failure
    assert caught.value is failure
