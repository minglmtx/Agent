"""Task RPC shares original registered site, scope, authority and failure exit."""

from datetime import datetime, timezone
from typing import Any
import pytest
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.adapters.sites.worker_protocol import (
    SiteWorkerCommand,
    decode_command,
    decode_reply,
)
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from site_worker_fixtures import case, operation
from test_site_task_execution import request
from test_slurm_commands import guard


def ready() -> Any:
    values = case()
    _, _, _, client, _ = values
    op = operation(client.configuration)
    client.configure(op, control=guard())
    client.start(op, control=guard())
    return values


def test_task_roundtrip_and_original_close_after_multiple_calls() -> None:
    instance, service, channel, client, authority = ready()
    for i in range(3):
        r = request("inspect" if i else "prepare", f"task-{i}")
        result = client.execute_task(r, control=guard())
        assert (
            result.request_sha256 == r.digest
            and result.private_result == '{"unit":true}'
        )
        assert client.state == "ready"
    assert [decode_command(v).sequence for v in channel.calls] == [1, 2, 3, 4, 5]
    assert authority.calls == ["configure", "start", "task", "task", "task"]
    assert client.start_operation is not None
    client.close(
        client.start_operation.cleanup(
            "site-close", now=datetime.now(timezone.utc), seconds=30
        ),
        control=guard(),
    )
    assert service.closed and instance.calls == [
        "start",
        "task",
        "task",
        "task",
        "stop",
    ]
    assert decode_command(channel.calls[-1]).sequence == 6


@pytest.mark.parametrize("stage", ["new", "configured", "closed"])
def test_task_requires_live_started_site(stage: str) -> None:
    instance, service, channel, client, authority = case()
    op = operation(client.configuration)
    if stage != "new":
        client.configure(op, control=guard())
    if stage == "closed":
        client.close(
            op.cleanup("close", now=datetime.now(timezone.utc), seconds=30),
            control=guard(),
        )
    before = len(channel.calls)
    with pytest.raises(InvalidTransition):
        client.execute_task(request(), control=guard())
    assert len(channel.calls) == before and "task" not in instance.calls


def test_task_authority_rejection_has_no_send() -> None:
    instance, _, channel, client, authority = ready()
    authority.error = PermissionError("no original task intent")
    with pytest.raises(PermissionError):
        client.execute_task(request(), control=guard())
    assert (
        len(channel.calls) == 2
        and instance.calls == ["start"]
        and client.state == "ready"
    )


@pytest.mark.parametrize("field", ["run_id", "owner_id", "allocation_id"])
def test_foreign_scope_cannot_send(field: str) -> None:
    instance, _, channel, client, _ = ready()
    r = request()
    r = r.model_copy(
        update={"operation": r.operation.model_copy(update={field: "other"})}
    )
    with pytest.raises(OwnershipConflict):
        client.execute_task(r, control=guard())
    assert len(channel.calls) == 2 and instance.calls == ["start"]


def test_replayed_task_operation_closes_original_without_second_effect() -> None:
    instance, service, channel, client, _ = ready()
    r = request()
    client.execute_task(r, control=guard())
    with pytest.raises(SiteWorkerFailure):
        client.execute_task(r, control=guard())
    assert (
        instance.calls == ["start", "task", "stop"]
        and service.closed
        and client.state == "quarantined"
    )


def test_task_native_failure_preserves_error_and_closes_original() -> None:
    instance, service, channel, client, _ = ready()
    instance.error = OSError("native failure")
    with pytest.raises(SiteWorkerFailure) as caught:
        client.execute_task(request(), control=guard())
    assert caught.value.reply.error is not None
    assert caught.value.reply.error.type_name == "OSError"
    assert instance.calls == ["start", "task", "stop"] and service.closed
    assert client.prepared is not None


def test_task_reply_cannot_change_original_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance, service, channel, client, _ = ready()
    monkeypatch.setattr(
        instance,
        "execute_task",
        lambda *a, **kw: SiteTaskResult(request_sha256="0" * 64, private_result="{}"),
    )
    with pytest.raises(SiteWorkerFailure):
        client.execute_task(request(), control=guard())
    assert service.closed and client.state == "quarantined"


@pytest.mark.parametrize("change", ["missing", "operation", "sequence", "old"])
def test_task_wire_wrong_shape_rejected(change: str) -> None:
    r = request()
    v = dict(
        session_id="site-session",
        sequence=3,
        phase="task",
        operation=r.operation,
        remaining_seconds=30.0,
        task=r,
    )
    if change == "missing":
        v["task"] = None
    elif change == "operation":
        v["operation"] = r.operation.model_copy(update={"operation_id": "changed"})
    elif change == "sequence":
        v["sequence"] = 2
    else:
        v["schema_version"] = "site-worker-command/3"
    with pytest.raises(ValueError):
        SiteWorkerCommand.model_validate(v)


def test_task_result_digest_is_checked_even_with_other_wire_fields_correct() -> None:
    _, _, channel, client, _ = ready()
    r = request()
    client.execute_task(r, control=guard())
    command = decode_command(channel.calls[-1])
    reply = client.last_reply
    assert reply is not None and reply.task_result is not None
    bad = reply.model_copy(
        update={
            "task_result": reply.task_result.model_copy(
                update={"request_sha256": "0" * 64}
            )
        }
    )
    with pytest.raises(ValueError):
        decode_reply(command, client.configuration, bad.model_dump_json().encode())


def test_restore_has_independent_cleanup_budget_after_execution_expired() -> None:
    import time
    from datetime import timedelta

    _, service, channel, client, _ = ready()
    original = request()
    original = original.model_copy(
        update={
            "operation": original.operation.model_copy(
                update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=1)}
            )
        }
    )
    client.execute_task(original, control=guard())
    time.sleep(1.05)
    cleanup = original.operation.cleanup(
        "restore-original", now=datetime.now(timezone.utc), seconds=30
    )
    restore = original.model_copy(update={"action": "restore", "operation": cleanup})
    result = client.execute_task(restore, control=guard())
    assert result.request_sha256 == restore.digest and not service.closed
    sent = decode_command(channel.calls[-1])
    assert (
        sent.operation.mode == "cleanup"
        and sent.operation.parent_operation_id == original.operation.operation_id
    )


@pytest.mark.parametrize(
    "change",
    [
        "old_request",
        "restore_execute",
        "prepare_cleanup",
        "snapshot_reference",
        "missing_snapshot",
    ],
)
def test_recovery_request_shape_rejected_before_send(change: str) -> None:
    from lab_generate_skill.domain.site_task import SiteTaskRequest

    r = request()
    data = r.model_dump()
    if change == "old_request":
        data["schema_version"] = "site-task-request/1"
    elif change == "restore_execute":
        data["action"] = "restore"
    elif change == "prepare_cleanup":
        data["operation"] = r.operation.cleanup(
            "wrong-mode", now=datetime.now(timezone.utc), seconds=30
        )
    elif change == "snapshot_reference":
        data["action"] = "snapshot"
    else:
        data["snapshot_ref"] = None
    with pytest.raises(ValueError):
        SiteTaskRequest.model_validate(data)
