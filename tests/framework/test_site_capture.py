"""Original guarded RPC and durable caller intent, with explicit synthetic site."""

import hashlib
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.worker_protocol import (
    decode_command,
    SiteWorkerCommand,
)
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from evidence_control_fixtures import EvidenceFixtureStore
from site_resume_fixtures import put
from test_site_task_wire import ready
from test_site_task_execution import request
from test_slurm_commands import guard


class Authority:
    def __init__(self, store: EvidenceFixtureStore) -> None:
        self.store, self.deny, self.calls = store, False, 0

    def verify_capture(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        self.calls += 1
        intent = SiteCaptureIntent.model_validate_json(
            self.store.read(intent_ref, control)
        )
        if (
            intent.request != request
            or intent.configuration_sha256
            != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict("capture differs from original durable intent")
        if self.deny:
            raise PermissionError("capture denied")


def case(root: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    instance, service, channel, client, _ = ready()
    store = EvidenceFixtureStore(root)
    req = SiteCaptureRequest(
        inspection=request("inspect", "capture"),
        collector_id="admin-product-catalog",
        collector_version="1",
    )
    intent = put(
        store,
        SiteCaptureIntent(
            configuration_sha256=hashlib.sha256(
                client.configuration.model_dump_json().encode()
            ).hexdigest(),
            request=req,
        ),
    )

    def capture(
        request: SiteCaptureRequest, *, control: OperationControl
    ) -> SiteTaskResult:
        instance.calls.append("capture")
        if instance.error:
            raise instance.error
        return SiteTaskResult(
            request_sha256=request.digest, private_result='{"captured":true}'
        )

    monkeypatch.setattr(instance, "capture_task", capture, raising=False)
    return instance, service, channel, client, req, intent, Authority(store)


def test_exact_capture_once_with_original_task_schema_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, service, channel, client, req, intent, authority = case(
        tmp_path, monkeypatch
    )
    result = client.capture_task(req, intent, authority, control=guard())
    assert result.request_sha256 == req.digest and authority.calls == 1
    sent = decode_command(channel.calls[-1])
    assert sent.schema_version == "site-worker-command/8"
    assert sent.capture_request == req and sent.capture_intent_ref == intent
    assert req.inspection.schema_version == "site-task-request/2"
    before = len(channel.calls)
    with pytest.raises(InvalidTransition):
        client.capture_task(req, intent, authority, control=guard())
    assert len(channel.calls) == before and instance.calls == ["start", "capture"]
    service.close(guard())


@pytest.mark.parametrize(
    "failure", ["denied", "wrong_intent", "native", "wire", "unsupported"]
)
def test_capture_failures_preserve_no_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    instance, service, channel, client, req, intent, authority = case(
        tmp_path, monkeypatch
    )
    if failure == "denied":
        authority.deny = True
    elif failure == "wrong_intent":
        req = req.model_copy(update={"collector_version": "foreign"})
    elif failure == "native":
        instance.error = OSError("capture unavailable")
    elif failure == "wire":
        channel.bad_reply = b"{}"
    else:
        monkeypatch.delattr(instance, "capture_task")
    with pytest.raises(
        (PermissionError, OwnershipConflict, SiteWorkerFailure, ValueError)
    ):
        client.capture_task(req, intent, authority, control=guard())
    if failure in ("denied", "wrong_intent"):
        assert instance.calls == ["start"] and len(channel.calls) == 2
        service.close(guard())
    else:
        assert service.closed and client.state == "quarantined"
        before = len(channel.calls)
        with pytest.raises(InvalidTransition):
            client.capture_task(req, intent, authority, control=guard())
        assert len(channel.calls) == before


@pytest.mark.parametrize(
    "change",
    [
        "missing_capture",
        "missing_intent",
        "wrong_operation",
        "wrong_phase",
        "old_wire",
        "old_reply",
        "wrong_return",
    ],
)
def test_capture_wire_shape_and_original_result_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    _, service, channel, client, req, intent, authority = case(tmp_path, monkeypatch)
    client.capture_task(req, intent, authority, control=guard())
    command = decode_command(channel.calls[-1])
    data = command.model_dump()
    if change == "missing_capture":
        data["capture_request"] = None
    elif change == "missing_intent":
        data["capture_intent_ref"] = None
    elif change == "wrong_operation":
        data["operation"] = command.operation.model_copy(
            update={"operation_id": "foreign"}
        )
    elif change == "wrong_phase":
        data["phase"] = "task"
    elif change == "old_wire":
        data["schema_version"] = "site-worker-command/5"
    else:
        from lab_generate_skill.adapters.sites.worker_protocol import decode_reply

        reply = client.last_reply
        assert reply is not None and reply.capture_result is not None
        values = (
            {"schema_version": "site-worker-reply/5"}
            if change == "old_reply"
            else {
                "capture_result": reply.capture_result.model_copy(
                    update={"request_sha256": "f" * 64}
                )
            }
        )
        with pytest.raises(ValueError):
            decode_reply(
                command,
                client.configuration,
                reply.model_copy(update=values).model_dump_json().encode(),
            )
        service.close(guard())
        return
    with pytest.raises(ValueError):
        SiteWorkerCommand.model_validate(data)
    service.close(guard())


def test_capture_rejects_effectful_task_identity() -> None:
    with pytest.raises(ValueError):
        SiteCaptureRequest(
            inspection=request(),
            collector_id="admin-product-catalog",
            collector_version="1",
        )
