"""Check slow admission, actual dispatch and persistence against original once facts."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.models.actor_worker_protocol import decode_command
from lab_generate_skill.adapters.models.local_actor import LocalActorUnconfirmed
from lab_generate_skill.application.actor_generation import (
    ActorDispatchFailure,
    execute_actor_generation,
)
from lab_generate_skill.application.actor_generation_control import (
    generation_preparation_control,
)
from lab_generate_skill.application.actor_loop import (
    ActorLoopFailure,
    RecordedActorRunner,
)
from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_generation_window_fixtures import dispatch, new_model, window_case


def test_slow_preflight_and_last_gate_leave_full_core_window_and_bounded_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, clock, _ = window_case(tmp_path)
    verify, exchange, put = c.authority.verify, c.channel.exchange, c.loop.store.put
    remaining: list[float] = []
    save_remaining: list[float] = []
    gate = 0
    tokenizations = 0
    tokenize = c.loader.session.tokenize

    def counted_tokens(*args: Any) -> tuple[int, ...]:
        nonlocal tokenizations
        tokenizations += 1
        return tokenize(*args)

    def admission(*args: Any) -> None:
        nonlocal gate
        verify(*args)
        gate += 1
        clock.sleep(3)

    def timed_exchange(raw: bytes, control: OperationControl) -> bytes:
        command = decode_command(raw)
        if command.operation == "validate":
            clock.sleep(8)
        elif command.operation == "generate":
            assert command.prepared_generation == "actor-prepared-generation/1"
            remaining.append(command.remaining_seconds)
            assert control.checkpoint() == 10
        reply = exchange(raw, control)
        if command.operation == "generate":
            clock.sleep(9)
        return reply

    def timed_put(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if metadata.content_schema == "actor-worker-command/1":
            assert control is not None
            save_remaining.append(control.checkpoint())
            clock.sleep(2)
        return put(raw, metadata, control, exchange_id=exchange_id)

    monkeypatch.setattr(c.authority, "verify", admission)
    monkeypatch.setattr(c.channel, "exchange", timed_exchange)
    monkeypatch.setattr(c.loop.store, "put", timed_put)
    monkeypatch.setattr(c.loader.session, "tokenize", counted_tokens)
    original = c.intent.operation.model_dump_json()
    result = execute_actor_generation(
        dispatch(c), c.loop.journal, c.model, c.loop.journal.controls, clock=clock
    )
    assert gate == 3 and remaining == [10] and save_remaining == [15]
    assert tokenizations == 1
    assert clock.elapsed == 28 and c.loader.session.calls == 1
    timing = c.authority.completed[0].dispatch_timing
    assert timing is not None and c.intent.execution_window is not None
    assert timing.started_at == c.intent.execution_window.prepared_at + timedelta(
        seconds=17
    )
    assert timing.operation.parent_operation_id == c.intent.operation.operation_id
    assert timing.operation.deadline == timing.started_at + timedelta(seconds=10)
    assert c.intent.operation.model_dump_json() == original
    assert result.events[-1].operation.deadline == clock.utcnow() + timedelta(
        seconds=15
    )
    generation = result.project().generation
    assert generation is not None and c.intent.matches(generation)
    assert len(list(c.root.glob("*.local-actor-call.json"))) == 1


@pytest.mark.parametrize("fault", ["expiry", "revoke", "cancel"])
def test_final_dynamic_gate_blocks_send_and_preserves_consumed_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c, clock, cancel = window_case(tmp_path)
    verify = c.authority.verify
    gates = 0

    def admission(*args: Any) -> None:
        nonlocal gates
        gates += 1
        if gates == 3:
            if fault == "expiry":
                clock.sleep(20)
            elif fault == "revoke":
                c.authority.denied = True
            else:
                cancel.cancelled = True
        verify(*args)

    monkeypatch.setattr(c.authority, "verify", admission)
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(
            dispatch(c), c.loop.journal, c.model, c.loop.journal.controls, clock=clock
        )
    failed = caught.value.primary
    assert isinstance(failed, LocalActorUnconfirmed)
    assert failed.phase == "before_send" and failed.dispatch_timing is None
    assert isinstance(
        failed.primary, PermissionError if fault == "revoke" else OperationStopped
    )
    assert (
        c.loader.session.calls == 0
        and len(list(c.root.glob("*.local-actor-call.json"))) == 1
    )
    assert c.loop.journal.read(c.authority.read_op).project().intent == c.intent
    # Reinstatement of current authority never grants a second send permit.
    c.authority.denied = cancel.cancelled = False
    if fault != "expiry":
        with pytest.raises(LocalActorUnconfirmed) as repeated:
            new_model(c, clock).generate(
                c.intent, control=c.loop.journal.controls.bind(c.intent.operation)
            )
        assert isinstance(repeated.value.primary, DispatchAlreadyCommitted)
    assert c.loader.session.calls == 0


def test_preparation_expiry_before_intent_has_no_consumption_or_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, clock, _ = window_case(tmp_path)
    original = c.channel.exchange

    def delayed(raw: bytes, control: OperationControl) -> bytes:
        if decode_command(raw).operation == "validate":
            clock.sleep(20)
        return original(raw, control)

    monkeypatch.setattr(c.channel, "exchange", delayed)
    with pytest.raises(ActorDispatchFailure):
        execute_actor_generation(
            dispatch(c), c.loop.journal, c.model, c.loop.journal.controls, clock=clock
        )
    assert c.loop.journal.read(c.authority.read_op).revision == 0
    assert not list(c.root.iterdir()) and c.loader.session.calls == 0


@pytest.mark.parametrize("fault", ["unknown", "save", "save-expiry"])
def test_sent_or_returned_failure_retains_window_and_never_repeats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c, clock, _ = window_case(tmp_path)
    exchange, put = c.channel.exchange, c.loop.store.put
    lost = OSError("original acknowledgement lost")

    def failed_exchange(raw: bytes, control: OperationControl) -> bytes:
        reply = exchange(raw, control)
        if decode_command(raw).operation == "generate" and fault == "unknown":
            raise lost
        return reply

    def failed_put(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        actual = put(raw, metadata, control, exchange_id=exchange_id)
        if metadata.content_schema == "actor-worker-command/1":
            if fault == "save":
                raise lost
            if fault == "save-expiry":
                clock.sleep(15)
        return actual

    monkeypatch.setattr(c.channel, "exchange", failed_exchange)
    monkeypatch.setattr(c.loop.store, "put", failed_put)
    with pytest.raises(ActorDispatchFailure) as caught:
        execute_actor_generation(
            dispatch(c), c.loop.journal, c.model, c.loop.journal.controls, clock=clock
        )
    failed = caught.value.primary
    assert (
        isinstance(failed, LocalActorUnconfirmed) and failed.dispatch_timing is not None
    )
    assert c.loader.session.calls == 1
    assert c.loop.journal.read(c.authority.read_op).project().intent == c.intent
    if fault != "unknown":
        assert failed.exchange is not None and failed.retained
        assert c.loop.store.read(failed.retained[-1])
    with pytest.raises(LocalActorUnconfirmed) as repeated:
        new_model(c, clock).generate(
            c.intent, control=c.loop.journal.controls.bind(c.intent.operation)
        )
    assert isinstance(repeated.value.primary, DispatchAlreadyCommitted)
    assert c.loader.session.calls == 1


@pytest.mark.parametrize("enough", [True, False])
def test_actual_loop_selects_windows_or_stops_before_starting_turn(
    tmp_path: Path, enough: bool
) -> None:
    c, clock, _ = window_case(tmp_path)
    c.loader.session.output = c.loader.session.output.model_copy(
        update={"text": '{"action":"send_msg_to_user(\'Saved\')"}'}
    )
    request = ActorRunRequest.model_validate(
        c.loop.request.model_copy(
            update={
                "operation": c.loop.request.operation.model_copy(
                    update={
                        "deadline": clock.utcnow()
                        + timedelta(seconds=200 if enough else 60)
                    }
                ),
                "generation_budgets": ActorGenerationBudgets(
                    preparation_seconds=20, execution_seconds=10
                ),
                "model_allocation": c.binding.resource,
                "parameters_refs": (c.intent.parameters_ref,)
                * len(c.loop.request.parameters_refs),
            }
        )
    )
    runner = RecordedActorRunner(
        replace(
            c.loop.runner.deps,
            model=c.model,
            clock=clock,
            controls=c.loop.journal.controls,
        )
    )
    if enough:
        result = runner.run(request)
        sealed = result.project().sealed
        assert sealed is not None and sealed.stop_reason == "finished"
        assert c.loader.session.calls == 1 and c.loop.browser.calls == 1
        timing = c.authority.completed[0].dispatch_timing
        assert timing is not None
        assert timing.operation.deadline - timing.started_at == timedelta(seconds=10)
    else:
        with pytest.raises(ActorLoopFailure) as caught:
            runner.run(request)
        assert isinstance(caught.value.primary, OperationStopped)
        assert c.loader.session.calls == c.loop.browser.calls == 0
        assert not list(c.root.iterdir())


@pytest.mark.parametrize(
    "bad", [True, -1.0, float("inf"), float("nan"), 10**400, "1", None]
)
def test_preparation_wait_rejects_invalid_duration_without_spending_time(
    tmp_path: Path, bad: object
) -> None:
    c, clock, _ = window_case(tmp_path)
    control = generation_preparation_control(
        c.intent.operation,
        c.intent.execution_window,
        c.loop.journal.controls.bind(c.intent.operation),
    )
    with pytest.raises((TypeError, ValueError)):
        control.wait(cast(float, bad))
    assert clock.elapsed == 0 and control.checkpoint() == 20


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"preparation_seconds": 0, "execution_seconds": 10},
        {"preparation_seconds": 20, "execution_seconds": 601},
        {"preparation_seconds": True, "execution_seconds": 10},
    ],
)
def test_invalid_selection_rejected(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ActorGenerationBudgets.model_validate(values)


def test_legacy_request_wire_omits_unselected_windows(tmp_path: Path) -> None:
    c, _, _ = window_case(tmp_path)
    assert "generation_budgets" not in c.loop.request.model_dump()
    assert (
        ActorRunRequest.model_validate_json(c.loop.request.model_dump_json())
        == c.loop.request
    )


@pytest.mark.parametrize("selection", ["same", "missing", "changed"])
def test_real_trace_admission_requires_original_selected_windows(
    tmp_path: Path, selection: str
) -> None:
    from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
    from lab_generate_skill.application.actor_model_admission import TraceActorAuthority
    from lab_generate_skill.domain.errors import OwnershipConflict
    from test_actor_model_admission import bound

    c, clock, _ = window_case(tmp_path)
    request, _, _ = bound(c)
    if selection != "missing":
        request = ActorRunRequest.model_validate(
            request.model_copy(
                update={
                    "generation_budgets": ActorGenerationBudgets(
                        preparation_seconds=20 if selection == "same" else 19,
                        execution_seconds=10,
                    ),
                }
            )
        )
    d = c.loop.runner.deps
    authority = TraceActorAuthority(
        request,
        c.loop.journal,
        c.loop.store,
        d.observations,
        d.project,
        c.loop.authority,
        c.loop.journal.controls,
    )
    model = RecordedLocalActorModel(
        c.root,
        c.binding,
        c.client,
        c.loop.store,
        c.loop.journal.controls,
        authority,
        clock=clock,
        prepare_control=generation_preparation_control,
    )
    if selection == "same":
        result = execute_actor_generation(
            dispatch(c), c.loop.journal, model, c.loop.journal.controls, clock=clock
        )
        assert result.project().generation is not None and c.loader.session.calls == 1
    else:
        with pytest.raises(ActorDispatchFailure) as caught:
            execute_actor_generation(
                dispatch(c), c.loop.journal, model, c.loop.journal.controls, clock=clock
            )
        assert isinstance(caught.value.primary, OwnershipConflict)
        assert c.loop.journal.read(c.authority.read_op).revision == 0
        assert not list(c.root.iterdir()) and c.loader.session.calls == 0


def test_selected_window_requires_injected_preparation_guard_before_any_call(
    tmp_path: Path,
) -> None:
    c, clock, _ = window_case(tmp_path)
    c.model._prepare_control = None
    with pytest.raises(ValueError, match="preparation guard"):
        c.model.validate(
            c.intent, control=c.loop.journal.controls.bind(c.intent.operation)
        )
    assert c.loader.session.calls == 0 and not list(c.root.iterdir())
