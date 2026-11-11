"""Actual loopback HTTP child + shared budget + CAS, without remote API calls."""

import base64
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.models.openrouter import OpenRouterTransport
from lab_generate_skill.adapters.models.paid_sender import LedgerModelSender
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, EvidenceNotFound
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_response import (
    ModelSendUnconfirmed,
    ModelTransportFailure,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_file_request_ledger import NoCancel
from openrouter_fixtures import fixture, resolved, provider, transport, KEY, REPLY


def test_real_http_sender_exact_payload_response_settlement_and_no_second_send(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    with provider() as server:
        backend = transport(f, server.endpoint)
        sender = LedgerModelSender(
            f.ledger,
            backend,
            f.store,
            OperationGuards(SystemClock(), NoCancel()),
            f.authority,
        )
        result = sender.generate(f.plan)
        assert result.settlement.record.charged.units == 2
        assert f.store.read(result.fact.response_ref) == REPLY
        assert len(server.requests) == 1
        path, body, authorization = server.requests[0]
        assert path == "/api/v1/chat/completions" and authorization == "Bearer " + KEY
        assert json.loads(body)["model"] == f.plan.reservation.request.model_id
        assert (
            KEY.encode() not in body
            and b"authorization_id" not in body
            and b"owner" not in body
        )
        with pytest.raises(ModelSendUnconfirmed) as error:
            sender.generate(f.plan)
        assert isinstance(error.value.__cause__, DispatchAlreadyCommitted)
        assert sender.reconcile(f.plan, result.fact_ref, f.cleanup()) == result
        assert len(server.requests) == 1


@pytest.mark.parametrize("status", [301, 307, 401, 402, 429, 500, 503])
def test_http_errors_redirects_and_retry_after_never_retry(
    tmp_path: Path, status: int
) -> None:
    f = fixture(tmp_path)
    with provider() as server:
        server.status, server.body = status, b'{"error":"unit-provider-rejection"}'
        sender = LedgerModelSender(
            f.ledger,
            transport(f, server.endpoint),
            f.store,
            OperationGuards(SystemClock(), NoCancel()),
            f.authority,
        )
        with pytest.raises(ModelSendUnconfirmed) as error:
            sender.generate(f.plan)
        assert error.value.transport_ref is not None
        record = json.loads(f.store.read(error.value.transport_ref))
        assert record["status"] == status and record["reason"] == "HTTP_STATUS"
        assert base64.b64decode(record["body_base64"]) == server.body
        assert KEY not in json.dumps(record)
        assert len(server.requests) == 1
        assert f.ledger.read(f.plan.reservation.request, f.cleanup()).held.units == 4


@pytest.mark.parametrize(
    "mode", ["malformed", "embedded_error", "oversize", "truncated", "credential_echo"]
)
def test_failed_response_capture_preserves_available_bytes_and_never_success(
    tmp_path: Path, mode: str
) -> None:
    f = fixture(tmp_path)
    with provider() as server:
        server.body = {
            "malformed": b"not json",
            "embedded_error": b'{"error":{"message":"unit"},"usage":{"cost":1}}',
            "oversize": b"x" * 1025,
            "truncated": REPLY,
            "credential_echo": KEY.encode(),
        }[mode]
        server.truncated = mode == "truncated"
        with pytest.raises(ModelTransportFailure) as error:
            transport(f, server.endpoint).send(resolved(f), f.plan.operation)
        record = json.loads(f.store.read(error.value.reference))
        expected = b"" if mode == "credential_echo" else server.body[:1024]
        assert base64.b64decode(record["body_base64"]) == expected
        assert len(server.requests) == 1 and KEY not in json.dumps(record)
        assert record["reason"] == (
            "RESPONSE_PROTOCOL"
            if mode in ("malformed", "embedded_error")
            else "HTTP_IO"
        )


def test_http_stall_stops_under_absolute_deadline(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    with provider() as server:
        server.wait = True
        op = OperationContext.model_validate(
            f.plan.operation.model_copy(
                update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=0.8)}
            )
        )
        started = time.monotonic()
        with pytest.raises(ModelTransportFailure) as error:
            transport(f, server.endpoint).send(resolved(f), op)
        assert time.monotonic() - started < 4
        assert server.received.is_set() and len(server.requests) == 1
        record = json.loads(f.store.read(error.value.reference))
        assert record["reason"] in {"DEADLINE_EXCEEDED", "HTTP_IO"}


def test_invalid_backend_input_fails_before_budget_dispatch(tmp_path: Path) -> None:
    from model_sender_fixtures import send_fixture

    f = send_fixture(
        tmp_path
    )  # Generic sender fixture lacks required provider/token bounds.
    with provider() as server:
        sender = LedgerModelSender(
            f.ledger,
            transport(f, server.endpoint),
            f.store,
            OperationGuards(SystemClock(), NoCancel()),
            f.authority,
        )
        with pytest.raises(ValueError):
            sender.generate(f.plan)
        assert not server.requests
        with pytest.raises(EvidenceNotFound):
            f.ledger.read(f.plan.reservation.request, f.cleanup())


@pytest.mark.parametrize(
    "endpoint,test_mode",
    [
        ("http://openrouter.ai/api/v1/chat/completions", False),
        ("https://example.com/api/v1/chat/completions", False),
        ("http://127.0.0.1:1234/api/v1/chat/completions", False),
        ("http://example.com:1234/api/v1/chat/completions", True),
        ("http://secret@127.0.0.1:1234/api/v1/chat/completions", True),
        ("http://127.0.0.1:1234/api/v1/chat/completions?key=x", True),
        ("http://127.0.0.1:1234/other", True),
    ],
)
def test_endpoint_cannot_leak_credentials_or_enable_insecure_production(
    tmp_path: Path, endpoint: str, test_mode: bool
) -> None:
    f = fixture(tmp_path)
    with pytest.raises(ValueError):
        OpenRouterTransport(
            KEY,
            f.store,
            OperationGuards(SystemClock(), NoCancel()),
            endpoint=endpoint,
            test_loopback=test_mode,
        )


@pytest.mark.parametrize(
    "key", [None, "", "with space", "header\r\nx", "é", "x" * 4097]
)
def test_bad_credentials_rejected_without_echo(tmp_path: Path, key: object) -> None:
    f = fixture(tmp_path)
    with pytest.raises(ValueError, match="Invalid memory credential"):
        OpenRouterTransport(
            cast(str, key), f.store, OperationGuards(SystemClock(), NoCancel())
        )
