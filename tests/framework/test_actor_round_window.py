"""Explicit effective preparation bounds; original actual dispatch stays whole."""

from datetime import datetime, timedelta
import json, os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from actor_generation_window_fixtures import window_case, new_model, dispatch
from test_lifecycle import ManualClock, CancelSwitch
from lab_generate_skill.application.actor_generation import (
    execute_actor_generation,
    ActorDispatchFailure,
)
from lab_generate_skill.application.actor_generation_control import (
    generation_preparation_control,
)
from lab_generate_skill.adapters.models.actor_worker_protocol import decode_command
from lab_generate_skill.domain.actor_execution_window import (
    ActorGenerationWindow,
    ActorGenerationBudgets,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.runtime.lifecycle import OperationGuards


def test_frozen_policy_outputs_are_consumed_without_policy_or_original_actor_replay() -> (
    None
):
    root = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    stage = json.loads((root / "preparation-policy-stage-output.json").read_text())
    assert stage["engineering_fixture_only"] and not stage["runtime_or_training_grant"]
    rows: list[dict[str, Any]] = []
    with patch(
        "lab_generate_skill.policies.actor_preparation_budget.preparation_seconds",
        side_effect=AssertionError("Frozen policy producer must not rerun"),
    ) as producer:
        for row in stage["rows"]:
            limit = row["preparation_limit_seconds"]
            if limit is None:
                continue
            clock = ManualClock()
            clock.wall = datetime.fromisoformat(
                stage["prepared_at"].replace("Z", "+00:00")
            )
            budgets = ActorGenerationBudgets.model_validate_json(
                json.dumps(stage["original_budgets"])
            )
            window = ActorGenerationWindow(
                schema_version="actor-generation-window/2",
                budgets=budgets,
                prepared_at=clock.utcnow(),
                preparation_limit_seconds=limit,
            )
            op = OperationContext.model_validate_json(
                json.dumps(stage["original_generation_operation"])
            ).model_copy(
                update={
                    "operation_id": "isolated-window-" + str(len(rows)),
                    "deadline": clock.utcnow()
                    + timedelta(seconds=window.transaction_seconds),
                }
            )
            window.require_original(op)
            controls = OperationGuards(clock, CancelSwitch())
            guard = generation_preparation_control(op, window, controls.bind(op))
            assert guard.checkpoint() == limit
            clock.sleep(limit - 0.5)
            assert guard.checkpoint() == 0.5
            actual = window.dispatch_operation(op, clock.utcnow())
            assert (
                actual.deadline - clock.utcnow()
            ).total_seconds() == 600 and actual.deadline <= op.deadline
            clock.sleep(0.5)
            with pytest.raises(OperationStopped):
                guard.checkpoint()
            assert (
                window.budgets.model_dump() == budgets.model_dump()
                and window.preparation_limit_seconds == limit
            )
            rows.append(
                dict(
                    window=window.model_dump(mode="json"),
                    operation=op.model_dump(mode="json"),
                    hypothetical_dispatch=actual.model_dump(mode="json"),
                    engineering_only_no_send=True,
                )
            )
        assert producer.call_count == 0
    (root / "isolated-round-window-output.json").write_text(
        json.dumps(
            dict(
                engineering_fixture_only=True,
                runtime_or_training_grant=False,
                rows=rows,
                policy_producer_calls=0,
                original_source_model_browser_restore_calls=0,
            ),
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize(
    "version,limit,valid",
    [
        ("actor-generation-window/1", None, True),
        ("actor-generation-window/1", 5, False),
        ("actor-generation-window/2", None, False),
        ("actor-generation-window/2", 0, False),
        ("actor-generation-window/2", 21, False),
        ("actor-generation-window/2", True, False),
        ("actor-generation-window/2", 5, True),
    ],
)
def test_effective_limit_requires_exact_version_and_cannot_widen_selected_maximum(
    version: str, limit: Any, valid: bool
) -> None:
    clock = ManualClock()
    value = dict(
        schema_version=version,
        budgets=ActorGenerationBudgets(preparation_seconds=20, execution_seconds=10),
        prepared_at=clock.utcnow(),
        preparation_limit_seconds=limit,
    )
    if not valid:
        with pytest.raises(ValidationError):
            ActorGenerationWindow.model_validate(value)
        return
    window = ActorGenerationWindow.model_validate(value)
    wire = window.model_dump_json()
    assert ActorGenerationWindow.model_validate_json(wire) == window
    if version == "actor-generation-window/1":
        assert (
            "preparation_limit_seconds" not in json.loads(wire)
            and window.transaction_seconds == 30
        )
    else:
        assert window.transaction_seconds == 15


@pytest.mark.parametrize("fault", ["none", "slow-preflight", "late-final-gate"])
def test_actual_model_consumer_retains_full_dispatch_or_no_send_and_original_once_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c, clock, _ = window_case(tmp_path)
    old = c.intent.execution_window
    assert old is not None
    window = ActorGenerationWindow(
        schema_version="actor-generation-window/2",
        budgets=old.budgets,
        prepared_at=old.prepared_at,
        preparation_limit_seconds=4,
    )
    op = c.intent.operation.model_copy(
        update={"deadline": clock.utcnow() + timedelta(seconds=14)}
    )
    c.intent = c.intent.model_copy(update={"operation": op, "execution_window": window})
    c.model = new_model(c, clock)
    verify, exchange = c.authority.verify, c.channel.exchange
    gates = 0
    sent = []

    def current(*args: Any) -> None:
        nonlocal gates
        verify(*args)
        gates += 1
        if fault == "late-final-gate" and gates == 3:
            clock.sleep(5)

    def timed(raw: bytes, control: Any) -> bytes:
        command = decode_command(raw)
        if command.operation == "validate" and fault == "slow-preflight":
            clock.sleep(5)
        if command.operation == "generate":
            sent.append(command.remaining_seconds)
        return exchange(raw, control)

    monkeypatch.setattr(c.authority, "verify", current)
    monkeypatch.setattr(c.channel, "exchange", timed)
    if fault == "none":
        execute_actor_generation(
            dispatch(c), c.loop.journal, c.model, c.loop.journal.controls, clock=clock
        )
        assert sent == [10] and c.loader.session.calls == 1
    else:
        with pytest.raises(ActorDispatchFailure):
            execute_actor_generation(
                dispatch(c),
                c.loop.journal,
                c.model,
                c.loop.journal.controls,
                clock=clock,
            )
        assert sent == [] and c.loader.session.calls == 0
        consumed = list(c.root.glob("*.local-actor-call.json"))
        assert bool(consumed) == (fault == "late-final-gate")
