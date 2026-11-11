"""Durable capture ordering, readback and publication uncertainty, no replay."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.domain.errors import InvalidTransition, EvidenceIntegrityError
from lab_generate_skill.domain.site_task import SiteTaskResult
from test_site_capture import case
from evidence_control_fixtures import EvidenceFixtureStore
from test_slurm_commands import guard


def test_capture_persists_exact_intent_then_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, service, _, client, req, _, authority = case(tmp_path, monkeypatch)
    recorder = RecordedSiteCapture(client, authority.store, authority)
    ref = recorder.capture(req, control=guard())
    assert (
        SiteTaskResult.model_validate_json(authority.store.read(ref)) == recorder.result
    )
    assert recorder.intent_ref is not None and len(recorder.candidates) == 2
    assert instance.calls == ["start", "capture"]
    with pytest.raises(InvalidTransition):
        recorder.capture(req, control=guard())
    service.close(guard())


@pytest.mark.parametrize(
    "failure",
    [
        "intent-before",
        "intent-after",
        "intent-metadata",
        "intent-readback",
        "result-after",
        "result-metadata",
        "result-readback",
        "denied",
    ],
)
def test_publication_fault_retains_candidates_without_dispatch_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    instance, service, channel, client, req, _, authority = case(tmp_path, monkeypatch)
    store: EvidenceFixtureStore = authority.store
    recorder = RecordedSiteCapture(client, store, authority)
    original_put, original_read = store.put, store.read
    target = (
        "site-capture-intent/2"
        if failure.startswith("intent")
        else "site-task-result/1"
    )

    def put(data: bytes, metadata: Any, control: Any) -> Any:
        if metadata.content_schema != target:
            return original_put(data, metadata, control)
        if failure.endswith("before"):
            raise OSError("intent never acknowledged")
        ref = original_put(data, metadata, control)
        if failure.endswith("after"):
            raise OSError("publication acknowledgement lost")
        if failure.endswith("metadata"):
            return ref.model_copy(update={"producer": "foreign"})
        return ref

    def read(ref: Any, control: Any = None) -> bytes:
        if ref.content_schema == target and failure.endswith("readback"):
            return b"{}"
        return original_read(ref, control)

    monkeypatch.setattr(store, "put", put)
    monkeypatch.setattr(store, "read", read)
    authority.deny = failure == "denied"
    with pytest.raises((OSError, EvidenceIntegrityError, PermissionError)) as caught:
        recorder.capture(req, control=guard())
    assert getattr(caught.value, "capture_candidate_references") == tuple(
        recorder.candidates
    )
    assert getattr(caught.value, "capture_returned_result") == recorder.result
    assert instance.calls == (
        ["start", "capture"] if failure.startswith("result") else ["start"]
    )
    before = len(channel.calls)
    with pytest.raises(InvalidTransition):
        recorder.capture(req, control=guard())
    assert len(channel.calls) == before
    service.close(guard())
