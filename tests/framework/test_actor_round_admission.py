"""Actual loop and original once dispatcher; no source/initialization replay."""

from contextlib import ExitStack
from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch
import pytest

from actor_generation_window_fixtures import window_case
from lab_generate_skill.application.actor_loop import (
    ActorLoopFailure,
    RecordedActorRunner,
)
from lab_generate_skill.domain.actor_budget_stop import ActorRoundBudgetStopped
from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.errors import OperationStopped


def bounded_case(root: Path, seconds: int = 105) -> Any:
    c, clock, cancel = window_case(root)
    c.loader.session.output = c.loader.session.output.model_copy(
        update={"text": '{"action":"send_msg_to_user(\'Saved\')"}'}
    )
    request = ActorRunRequest.model_validate(
        c.loop.request.model_copy(
            update={
                "operation": c.loop.request.operation.model_copy(
                    update={"deadline": clock.utcnow() + timedelta(seconds=seconds)}
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
    return c, clock, cancel, request, runner


def test_actual_loop_selects_effective_window_and_consumes_frozen_window_output(
    tmp_path: Path,
) -> None:
    c, clock, _, request, runner = bounded_case(tmp_path)
    root = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    stage = json.loads((root / "frozen-window-input.json").read_text())
    assert stage["engineering_fixture_only"] and len(stage["rows"]) == 4
    with ExitStack() as stack:
        producers = [
            stack.enter_context(
                patch(name, side_effect=AssertionError("Frozen producer forbidden"))
            )
            for name in (
                "lab_generate_skill.adapters.sites.task_initialization.RecordedTaskInitialization.start",
                "lab_generate_skill.adapters.sites.task_finalization.RecordedTaskFinalization.restore",
            )
        ]
        final = runner.run(request)
        assert all(p.call_count == 0 for p in producers)
    sealed = final.project().sealed
    assert sealed is not None and sealed.stop_reason == "finished"
    generation = c.authority.completed[0]
    window = generation.call.intent.execution_window
    assert window is not None and window.schema_version == "actor-generation-window/2"
    assert (
        window.preparation_limit_seconds == 10
        and window.budgets.preparation_seconds == 20
    )
    assert (
        generation.dispatch_timing.operation.deadline
        - generation.dispatch_timing.started_at
        == timedelta(seconds=10)
    )
    assert generation.call.intent.operation.deadline < request.operation.deadline
    assert c.loader.session.calls == c.loop.browser.calls == 1
    (root / "actual-loop-stage-output.json").write_text(
        json.dumps(
            dict(
                engineering_fixture_only=True,
                runtime_or_training_grant=False,
                window=window.model_dump(mode="json"),
                trace=final.model_dump(mode="json"),
                source_initialize_restore_calls=0,
                actual_production_loop=True,
                synthetic_model_browser=True,
            ),
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("seconds", [95, 94, 1])
def test_known_unsent_admission_has_no_authority_or_model_effect(
    tmp_path: Path, seconds: int
) -> None:
    c, _, _, request, runner = bounded_case(tmp_path, seconds)
    with pytest.raises(ActorLoopFailure) as caught:
        runner.run(request)
    primary = caught.value.primary
    assert isinstance(primary, ActorRoundBudgetStopped)
    assert (
        primary.known_unsent
        and primary.stage == "admission"
        and primary.round_index == 0
    )
    assert c.loop.authority.calls == c.loader.session.calls == c.loop.browser.calls == 0
    assert caught.value.request_ref is None and not list(c.root.iterdir())


@pytest.mark.parametrize(
    "where",
    [
        "initial-authority",
        "round-authority",
        "initial-read",
        "initial-observation",
        "request-save",
    ],
)
def test_initial_setup_and_round_authority_share_effective_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    where: str,
) -> None:
    c, clock, _, request, runner = bounded_case(tmp_path)
    verify, read, load, put = (
        c.loop.authority.verify,
        c.loop.journal.read,
        runner.deps.observations.load,
        c.loop.store.put,
    )

    def authority(*args: Any) -> None:
        target = 0 if where == "initial-authority" else 1
        if c.loop.authority.calls == target and where.endswith("authority"):
            clock.sleep(10)
        verify(*args)

    def journal_read(op: Any) -> Any:
        if where == "initial-read" and op.mode == "execute":
            assert (op.deadline - clock.utcnow()).total_seconds() == 10
            clock.sleep(10)
        return read(op)

    def observation_load(ref: Any, op: Any) -> Any:
        if where == "initial-observation":
            assert (op.deadline - clock.utcnow()).total_seconds() == 10
            clock.sleep(10)
        return load(ref, op)

    def save(raw: Any, metadata: Any, control: Any = None, **kw: Any) -> Any:
        if where == "request-save" and metadata.content_schema.startswith(
            "actor-run-request/"
        ):
            assert control.checkpoint() == 10
            clock.sleep(10)
        return put(raw, metadata, control, **kw)

    monkeypatch.setattr(c.loop.authority, "verify", authority)
    monkeypatch.setattr(c.loop.journal, "read", journal_read)
    monkeypatch.setattr(runner.deps.observations, "load", observation_load)
    monkeypatch.setattr(c.loop.store, "put", save)
    with pytest.raises(ActorLoopFailure) as caught:
        runner.run(request)
    assert isinstance(caught.value.primary, ActorRoundBudgetStopped)
    assert caught.value.primary.stage == "preparation"
    assert isinstance(caught.value.primary.__cause__, OperationStopped)
    assert c.loader.session.calls == c.loop.browser.calls == 0
    assert not list(c.root.iterdir())


@pytest.mark.parametrize("fault", ["cancel", "revoke", "engineering"])
def test_other_preparation_failures_are_not_unsent_budget_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c, _, cancel, request, runner = bounded_case(tmp_path)
    if fault == "cancel":
        request = request.model_copy(
            update={
                "operation": request.operation.model_copy(
                    update={"cancellation_ref": c.intent.operation.cancellation_ref}
                )
            }
        )
    verify = c.loop.authority.verify

    def authority(*args: Any) -> None:
        if c.loop.authority.calls == 1:
            if fault == "cancel":
                cancel.cancelled = True
            elif fault == "revoke":
                c.loop.authority.denied = True
            else:
                raise OSError("engineering failure")
        verify(*args)

    monkeypatch.setattr(c.loop.authority, "verify", authority)
    with pytest.raises(ActorLoopFailure) as caught:
        runner.run(request)
    assert not isinstance(caught.value.primary, ActorRoundBudgetStopped)
    assert isinstance(
        caught.value.primary,
        (
            OperationStopped
            if fault == "cancel"
            else PermissionError if fault == "revoke" else OSError
        ),
    )
    assert c.loader.session.calls == c.loop.browser.calls == 0


def test_next_unsent_round_preserves_actual_return_action_and_bounded_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, clock, _, request, runner = bounded_case(tmp_path, 100)
    c.loader.session.output = c.loader.session.output.model_copy(
        update={"text": '{"action":"click(\'2\')"}'}
    )
    generate, step = c.model.generate, c.loop.browser.step

    def model(*args: Any, **kw: Any) -> Any:
        result = generate(*args, **kw)
        clock.sleep(8)
        return result

    def browser(*args: Any, **kw: Any) -> Any:
        result = step(*args, **kw)
        clock.sleep(8)
        return result

    monkeypatch.setattr(c.model, "generate", model)
    monkeypatch.setattr(c.loop.browser, "step", browser)
    with pytest.raises(ActorLoopFailure) as caught:
        runner.run(request)
    primary, snapshot = caught.value.primary, caught.value.snapshot
    assert isinstance(primary, ActorRoundBudgetStopped) and primary.round_index == 1
    assert snapshot is not None
    view = snapshot.project()
    assert view.sealed is not None and view.sealed.stop_reason == "error"
    assert view.sealed.generations == view.sealed.interactions == 1
    assert view.intent is None and view.turns[0].generation.status == "completed"
    assert c.loader.session.calls == c.loop.browser.calls == 1
    assert caught.value.cleanup_errors == ()
    with pytest.raises(ActorLoopFailure):
        runner.run(request)
    assert c.loader.session.calls == c.loop.browser.calls == 1
