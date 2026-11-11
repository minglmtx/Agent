"""Capture only original bytes; no model call and no writes before full validation."""

from lab_generate_skill.ports.lifecycle import OperationControl

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.models.generator_execution_capture import (
    record_generator_exchange,
)
from lab_generate_skill.adapters.models.generator_worker_exchange import (
    GeneratorWorkerExchange,
)
from lab_generate_skill.adapters.models.generator_worker_protocol import (
    decode_command,
    decode_reply,
)
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from generator_execution_fixtures import (
    ExecutionCase,
    e as e,
    execution_template as execution_template,
)
from generator_worker_fixtures import worker_case
from cgroup_fixtures import Control


def exchange(e: ExecutionCase) -> GeneratorWorkerExchange:
    return GeneratorWorkerExchange(
        e.store.read(e.record.command_ref), e.store.read(e.record.reply_ref)
    )


def capture(e: ExecutionCase, value: Any) -> Any:
    spec = GeneratorResourceSpec.model_validate_json(e.store.read(e.record.spec_ref))
    return record_generator_exchange(
        e.store,
        e.adapter,
        spec,
        e.record.acquired_ref,
        e.record.intent,
        e.record.guard,
        value,
        Control(),
    )


def test_capture_publish_repeat_and_read(e: ExecutionCase) -> None:
    observed = exchange(e)
    first = capture(e, observed)
    assert capture(e, observed) == first
    assert e.adapter.load(first.intent, Control()) == first
    assert e.adapter.output(first, Control()) == e.output
    assert e.store.read(first.command_ref) == observed.command
    assert e.store.read(first.reply_ref) == observed.reply


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        "exchange",
        GeneratorWorkerExchange(b"", b""),
        GeneratorWorkerExchange(b"{}", b"{}"),
    ],
)
def test_invalid_capture_has_no_write(
    e: ExecutionCase, value: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any) -> Any:
        pytest.fail("write before validation")

    monkeypatch.setattr(e.store, "put", forbidden)
    with pytest.raises((ValueError, TypeError)):
        capture(e, value)
    assert not list(e.root.iterdir())


@pytest.mark.parametrize("at", [1, 2, 3])
@pytest.mark.parametrize("committed", [False, True])
def test_publication_failure_retains_exact_original_exchange(
    e: ExecutionCase, at: int, committed: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    put = e.store.put
    failure = OSError("CAS failure")
    count = 0
    observed = exchange(e)

    def failing(
        raw: bytes, meta: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        nonlocal count
        count += 1
        if count == at:
            if committed:
                put(raw, meta)
            raise failure
        return put(raw, meta)

    with monkeypatch.context() as patch:
        patch.setattr(e.store, "put", failing)
        with pytest.raises(OSError) as caught:
            capture(e, observed)
    assert caught.value is failure
    assert getattr(failure, "generator_execution_exchange") is observed
    assert getattr(failure, "generator_execution_candidate").intent == e.record.intent
    assert not list(e.root.iterdir())
    # Re-publishing retained bytes cannot issue a model call: no engine dependency.
    result = capture(e, observed)
    assert e.adapter.load(e.record.intent, Control()) == result


def test_client_returns_exact_original_exchange_without_extra_generation(
    tmp_path: Path,
) -> None:
    engine, loader, request, parameters, control, service, channel, client = (
        worker_case(tmp_path)
    )
    observed = client.generate_exchange(request, parameters, control)
    assert observed.command == channel.sent[-1]
    command = decode_command(observed.command)
    reply = decode_reply(command, observed.reply)
    assert reply.output is not None and reply.output == observed.decoded_reply.output
    assert [decode_command(raw).operation for raw in channel.sent] == [
        "configure",
        "generate",
    ]
    before = tuple(channel.sent)
    assert observed.decoded_reply == reply and tuple(channel.sent) == before
    client.close(control)
    assert observed.decoded_reply == reply
