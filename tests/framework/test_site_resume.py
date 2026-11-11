"""Resume intent before send, exact wire/scope and unknown effect preservation."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.site_resume import SiteResumeRequest, SiteResumeResult
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.adapters.sites.worker_protocol import (
    decode_command,
    SiteWorkerCommand,
)
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from site_resume_fixtures import case
from test_slurm_commands import guard


def test_durable_resume_roundtrip_then_original_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, service, channel, client, store, authority, recorder, req = case(
        tmp_path, monkeypatch
    )
    ref = recorder.resume(req, control=guard())
    assert SiteResumeResult.model_validate_json(store.read(ref)) == recorder.result
    assert recorder.intent_ref is not None and authority.calls == 1
    sent = decode_command(channel.calls[-1])
    assert sent.phase == "resume" and sent.resume_intent_ref == recorder.intent_ref
    assert sent.schema_version == "site-worker-command/8"
    with pytest.raises(InvalidTransition):
        recorder.resume(req, control=guard())
    assert instance.calls == ["start", "resume"] and len(channel.calls) == 3
    service.close(guard())
    assert instance.calls[-1] == "stop"


@pytest.mark.parametrize(
    "failure",
    [
        "intent-before",
        "intent-after",
        "intent-metadata",
        "result-after",
        "result-metadata",
        "denied",
        "native",
        "wire",
    ],
)
def test_failures_keep_exact_unknown_without_resend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    instance, service, channel, client, store, authority, recorder, req = case(
        tmp_path, monkeypatch
    )
    original = store.put

    def put(data: bytes, metadata: Any, control: Any) -> Any:
        target = (
            "site-resume-intent/1"
            if failure.startswith("intent")
            else "site-resume-result/1"
        )
        if metadata.content_schema != target:
            return original(data, metadata, control)
        if failure == "intent-before":
            raise OSError("before intent")
        ref = original(data, metadata, control)
        if failure.endswith("after"):
            raise OSError("after commit")
        if failure.endswith("metadata"):
            return ref.model_copy(update={"producer": "wrong"})
        return ref

    monkeypatch.setattr(store, "put", put)
    if failure == "denied":
        authority.deny = True
    if failure == "native":
        instance.error = OSError("resume native failed")
    if failure == "wire":
        channel.bad_reply = b"{}"
    with pytest.raises(
        (
            OSError,
            ValueError,
            PermissionError,
            SiteWorkerFailure,
            EvidenceIntegrityError,
        )
    ) as caught:
        recorder.resume(req, control=guard())
    assert getattr(caught.value, "resume_intent_reference") == recorder.intent_ref
    assert getattr(caught.value, "resume_returned_result") == recorder.result
    if failure.startswith("intent") or failure == "denied":
        assert instance.calls == ["start"]
    elif failure in ("wire", "native"):
        assert service.closed and client.state == "quarantined"
    else:
        assert instance.calls == ["start", "resume"] and recorder.result is not None
    before = len(channel.calls)
    with pytest.raises(InvalidTransition):
        recorder.resume(req, control=guard())
    assert len(channel.calls) == before


@pytest.mark.parametrize(
    "field",
    [
        "run_id",
        "owner_id",
        "attempt_id",
        "allocation_id",
        "parent_operation_id",
        "recovery_ref",
        "mode",
    ],
)
def test_wrong_original_scope_rejected_without_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    instance, _, channel, _, _, _, recorder, req = case(tmp_path, monkeypatch)
    value: Any = "foreign"
    if field == "mode":
        value = "execute"
    if field == "recovery_ref":
        value = req.operation.recovery_ref.model_copy(update={"sha256": "f" * 64})
    wrong = req.model_copy(
        update={"operation": req.operation.model_copy(update={field: value})}
    )
    with pytest.raises((ValueError, OwnershipConflict)):
        recorder.resume(wrong, control=guard())
    assert len(channel.calls) == 2 and instance.calls == ["start"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "site-worker-command/4"),
        ("resume_intent_ref", None),
        ("resume", None),
        ("sequence", 2),
    ],
)
def test_resume_wire_rejects_missing_or_old_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    _, _, channel, _, _, _, recorder, req = case(tmp_path, monkeypatch)
    recorder.resume(req, control=guard())
    data = decode_command(channel.calls[-1]).model_dump()
    with pytest.raises(ValueError):
        SiteWorkerCommand.model_validate({**data, field: value})


def test_replayed_wire_operation_stops_original_without_second_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, service, _, client, _, authority, recorder, req = case(
        tmp_path, monkeypatch
    )
    recorder.resume(req, control=guard())
    assert recorder.intent_ref is not None
    with pytest.raises(SiteWorkerFailure):
        client.resume_frontend(req, recorder.intent_ref, authority, control=guard())
    assert instance.calls == ["start", "resume", "stop"] and service.closed
