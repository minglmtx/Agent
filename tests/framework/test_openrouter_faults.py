"""Post-response timeout/cleanup, persistence failures and cancellation retain facts."""

import base64
import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.http_worker import exchange
from lab_generate_skill.adapters.models.openrouter import OpenRouterTransport
from lab_generate_skill.adapters.processes.commands import (
    ProcessRunner,
    CommandCapture,
    CommandFailure,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext, CancellationRef
from lab_generate_skill.domain.model_response import ModelTransportFailure
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from openrouter_fixtures import fixture, resolved, provider, transport, KEY, REPLY


def test_full_response_survives_supervisor_timeout_and_cleanup_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fixture(tmp_path)
    packet = json.dumps(
        {
            "status": 200,
            "body_base64": base64.b64encode(REPLY).decode(),
            "complete": True,
            "errors": [],
        }
    ).encode()

    def stopped(
        self: ProcessRunner,
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        assert (
            KEY not in str(argv)
            and stdin_bytes is not None
            and KEY.encode() in stdin_bytes
        )
        raise ExceptionGroup(
            "late failure",
            [
                CommandFailure(
                    "DEADLINE_EXCEEDED", CommandCapture(argv, 0, packet, b"", False)
                ),
                OSError("cleanup"),
            ],
        )

    monkeypatch.setattr(ProcessRunner, "run", stopped)
    with pytest.raises(ModelTransportFailure) as error:
        transport(f, "http://127.0.0.1:1234/api/v1/chat/completions").send(
            resolved(f), f.plan.operation
        )
    record = json.loads(f.store.read(error.value.reference))
    assert (
        record["reason"] == "DEADLINE_EXCEEDED"
        and base64.b64decode(record["body_base64"]) == REPLY
    )
    assert isinstance(error.value.__cause__, ExceptionGroup)
    assert len(error.value.__cause__.exceptions) == 2


def test_http_failure_and_diagnostic_storage_failure_keep_both_causes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fixture(tmp_path)

    def fail(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        raise OSError("storage failed")

    with provider() as server:
        server.status = 503
        monkeypatch.setattr(f.store, "put", fail)
        with pytest.raises(ExceptionGroup) as error:
            transport(f, server.endpoint).send(resolved(f), f.plan.operation)
        assert isinstance(error.value.exceptions[0], ValueError)
        assert isinstance(error.value.exceptions[1], OSError)
        assert len(server.requests) == 1


def test_worker_preserves_response_and_both_close_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import http.client

    class Response:
        status = 200
        length = 0

        def read(self, amount: int) -> bytes:
            return REPLY

        def close(self) -> None:
            raise OSError("response close")

    class Connection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def request(self, *args: object, **kwargs: object) -> None:
            pass

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            raise OSError("connection close")

    monkeypatch.setattr(http.client, "HTTPConnection", Connection)
    packet = exchange(
        {
            "endpoint": "http://127.0.0.1:1/api/v1/chat/completions",
            "credential": KEY,
            "timeout": 1,
            "max_response_bytes": 1024,
            "body_base64": "e30=",
        }
    )
    assert packet["complete"] is False
    assert packet["errors"] == ["response_close_OSError", "connection_close_OSError"]
    assert base64.b64decode(packet["body_base64"]) == REPLY


def test_live_cancel_after_http_send_does_not_retry(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    with provider() as server:
        server.wait = True

        class Cancel:
            def is_cancelled(self, reference: CancellationRef) -> bool:
                return server.received.is_set()

        op = OperationContext.model_validate(
            f.plan.operation.model_copy(
                update={
                    "cancellation_ref": CancellationRef(
                        channel_id="cancel",
                        run_id=f.plan.operation.run_id,
                        owner_id=f.plan.operation.owner_id,
                    )
                }
            )
        )
        backend = OpenRouterTransport(
            KEY,
            f.store,
            OperationGuards(SystemClock(), Cancel()),
            endpoint=server.endpoint,
            test_loopback=True,
        )
        with pytest.raises(ModelTransportFailure) as error:
            backend.send(resolved(f), op)
        assert error.value.reason_code == "CANCELLED" and len(server.requests) == 1
