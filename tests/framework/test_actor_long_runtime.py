"""Long configuration across original wire/CAS/once/closed review, synthetic model."""

import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.actor_count_protocol import (
    decode_worker_command,
)
from lab_generate_skill.adapters.models.actor_worker_client import ActorWorkerFailure
from lab_generate_skill.adapters.models.actor_worker_protocol import ActorWorkerCommand
from lab_generate_skill.adapters.models.actor_context_records import (
    actor_context_document,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_context_count import ActorCountExecution
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.errors import (
    ActorInputBudgetExceeded,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.bootstrap.actor_context_review import closed_actor_context
from lab_generate_skill.bootstrap.actor_projection import build_actor_projection
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from actor_long_runtime_fixtures import long_counter_case
from actor_long_fixtures import long_config
from source_actor_context_fixtures import source_context_case
from source_actor_execution import execute_source_actor
from source_actor_projection import original_source_projection
from source_actor_review import review_actor
from source_review_records import ReadOnlyEvidence
from test_actor_count_evidence import reviewer
from test_run_journal import command


@pytest.mark.parametrize("count", [30825, 61439, 61440, 61441])
def test_long_original_wire_count_generate_and_closed_evidence(
    tmp_path: Path, count: int
) -> None:
    c = long_counter_case(tmp_path)
    prompt = ActorPrompt.model_validate_json(c.evidence.read(c.input_ref, c.control))
    c.loader.session.tokens = (1,) * count
    c.loader.session.output = c.loader.session.output.model_copy(
        update={"prompt_tokens": count}
    )
    counted = c.counter.measure(c.input_ref, c.profile, c.policy, control=c.control)
    assert counted.measurement.input_tokens == count
    assert c.loader.session.calls == 0
    execution = ActorCountExecution.model_validate_json(
        c.evidence.read(counted.evidence_ref, c.control)
    )
    assert c.evidence.read(execution.command_ref, c.control) == c.channel.sent[-1]
    if count > 61440:
        with pytest.raises(ActorInputBudgetExceeded):
            c.client.validate(prompt, c.parameters, c.control)
        with pytest.raises(ActorInputBudgetExceeded):
            c.client.generate(prompt, c.parameters, c.control)
        assert c.loader.session.calls == 0 and c.channel.aborts == 0
    else:
        c.client.validate(prompt, c.parameters, c.control)
        returned = c.client.generate(prompt, c.parameters, c.control)
        assert returned.prompt_tokens == count and c.loader.session.calls == 1
    read_only = reviewer(c)
    c.client.close(c.control)
    sent = len(c.channel.sent)
    verified = read_only.verify(counted, c.profile, c.policy, control=c.control)
    assert verified.input_tokens == count and len(c.channel.sent) == sent
    assert c.loader.loads == c.loader.session.closed == c.channel.finishes == 1
    commands = [decode_worker_command(raw) for raw in c.channel.sent]
    assert [x.sequence for x in commands] == list(range(1, len(commands) + 1))
    configure = commands[0]
    assert isinstance(configure, ActorWorkerCommand)
    assert configure.operation == "configure" and configure.config == long_config()
    assert configure.config.schema_version == "actor-engine-config/2"
    assert c.profile.output_reserve == 4096 and c.parameters.max_new_tokens == 4096


def test_long_wire_unknown_generation_is_not_resent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = long_counter_case(tmp_path)
    prompt = ActorPrompt.model_validate_json(c.evidence.read(c.input_ref, c.control))
    c.client.validate(prompt, c.parameters, c.control)
    exchange = c.channel.exchange
    error = OSError("unit accepted long generation, response acknowledgement lost")

    def unknown(raw: bytes, control: Any) -> bytes:
        exchange(raw, control)
        raise error

    monkeypatch.setattr(c.channel, "exchange", unknown)
    with pytest.raises(OSError) as caught:
        c.client.generate(prompt, c.parameters, c.control)
    assert caught.value is error and c.loader.session.calls == 1
    sent = len(c.channel.sent)
    with pytest.raises(OwnershipConflict):
        c.client.generate(prompt, c.parameters, c.control)
    assert len(c.channel.sent) == sent and c.loader.session.calls == 1
    assert c.loader.session.closed == 1 and c.channel.aborts == 1


def test_long_wire_duplicate_count_fails_closed_without_generation(
    tmp_path: Path,
) -> None:
    c = long_counter_case(tmp_path)
    c.counter.measure(c.input_ref, c.profile, c.policy, control=c.control)
    original = decode_worker_command(c.channel.sent[-1])
    reply = c.channel.service.handle(original)
    assert reply.status == "error" and c.channel.service.closed
    assert c.loader.session.calls == 0 and c.loader.session.closed == 1
    with pytest.raises(ActorWorkerFailure):
        c.client.close(c.control)


@pytest.mark.parametrize("reserve", [2048, 3482, 4095])
def test_long_wire_rejects_reduced_output_without_loading_or_retry(
    tmp_path: Path, reserve: int
) -> None:
    c = long_counter_case(tmp_path)
    prompt = ActorPrompt.model_validate_json(c.evidence.read(c.input_ref, c.control))
    parameters = c.parameters.model_copy(update={"max_new_tokens": reserve})
    with pytest.raises(ActorWorkerFailure) as caught:
        c.client.measure(prompt, parameters, c.control)
    assert caught.value.reply.error is not None
    assert caught.value.reply.error.type_name == "ValueError"
    assert c.loader.loads == c.loader.session.calls == 0
    sent = len(c.channel.sent)
    with pytest.raises(OwnershipConflict):
        c.client.measure(prompt, c.parameters, c.control)
    assert len(c.channel.sent) == sent


def test_long_count_cancellation_before_send_keeps_no_count_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = long_counter_case(tmp_path)
    sent = len(c.channel.sent)
    error = OperationStopped("CANCELLED", "unit-long-count")

    def stopped() -> float:
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(c.control, "checkpoint", stopped)
        with pytest.raises(OperationStopped) as caught:
            c.counter.measure(c.input_ref, c.profile, c.policy, control=c.control)
        assert caught.value is error
    assert len(c.channel.sent) == sent and c.loader.loads == c.loader.session.calls == 0
    c.client.close(c.control)


@pytest.mark.parametrize("value", [None, {}, [], "", True, 0])
def test_long_wire_invalid_empty_or_wrong_prompt_has_no_new_frame(
    tmp_path: Path, value: Any
) -> None:
    c = long_counter_case(tmp_path)
    sent = len(c.channel.sent)
    with pytest.raises(ValidationError):
        c.client.measure(value, c.parameters, c.control)
    assert len(c.channel.sent) == sent and c.loader.loads == c.loader.session.calls == 0
    c.client.close(c.control)


def test_long_source_default_assembly_counts_sends_and_independently_reviews_same_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch, engine_config=long_config())
    c.loader.session.tokens = (1,) * 30825
    c.loader.session.output = c.loader.session.output.model_copy(
        update={"prompt_tokens": 30825}
    )
    result, failure = execute_source_actor(
        c.source,
        c.browser,
        c.session,
        c.actor,
        c.scope,
        c.params,
        tmp_path / "attempt",
        context_policy=c.policy,
    )
    if failure is not None:
        (tmp_path / "source-long-failure.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        raise failure
    assert (
        result["generations"]
        == result["interactions"]
        == result["verified_model_returns"]
        == 1
    )
    assert c.loader.session.calls == c.session.calls == 1
    store = c.actor.evidence
    request = ActorRunRequest.model_validate_json(
        store.read(EvidenceRef.model_validate(result["planned_actor_request_ref"]))
    )
    snapshot = TraceSnapshot.model_validate_json(
        store.read(EvidenceRef.model_validate(result["trace_snapshot_ref"]))
    )
    executions = tuple(
        LocalActorExecution.model_validate_json(
            store.read(EvidenceRef.model_validate(x))
        )
        for x in result["executions"]
    )
    control = c.actor.controls.bind(request.operation)
    assert request.context_configuration_ref is not None
    config = actor_context_document(
        store,
        request.context_configuration_ref,
        "actor-context-configuration/1",
        ActorContextConfiguration,
        16 * 1024**2,
        control,
    )
    assert all(
        p.hard_limit == 61440 and p.output_reserve == 4096 and p.context_window == 65536
        for p in config.profiles
    )
    assert all(x.call.intent.context_preparation_ref is not None for x in executions)
    op = command("close-long-source-context", attempt=request.scope.attempt_id)
    c.client.close(c.actor.controls.bind(op))
    sent = len(c.channel.sent)
    readonly = ReadOnlyEvidence(tmp_path / "case")
    control = c.actor.controls.bind(op)
    project = original_source_projection(request, snapshot.plan, readonly, control)
    inputs = closed_actor_context(
        request,
        executions,
        readonly,
        EvidenceObservations(readonly, c.actor.controls),
        control=control,
    )
    summary = review_actor(
        request,
        snapshot,
        executions,
        readonly,
        c.actor.controls,
        op,
        project=build_actor_projection(project),
        context=inputs,
    )
    assert summary["generations"] == 1 and len(c.channel.sent) == sent
    assert c.loader.session.calls == c.loader.session.closed == 1
    assert c.resource_calls == [True, True, True, True, True, True, False]
