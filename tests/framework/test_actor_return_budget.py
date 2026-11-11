"""Selected persistence budget keeps real readback, original deadlines and once intent."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from actor_generation_window_fixtures import window_case
from test_actor_model_admission import bound
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.application.actor_generation_control import (
    generation_preparation_control,
)
from lab_generate_skill.domain.actor_dispatch import ActorDispatch
from lab_generate_skill.domain.trace_events import GenerationPlanned
from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.application.actor_generation import (
    execute_actor_generation,
    ActorDispatchFailure,
)
from lab_generate_skill.application.actor_loop import (
    RecordedActorRunner,
    ActorLoopFailure,
)


@pytest.mark.parametrize("selected", [False, True])
def test_slow_required_publications_have_explicit_bounded_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selected: bool
) -> None:
    c, clock, _ = window_case(tmp_path)
    if selected:
        window = c.intent.execution_window
        assert window is not None
        c.intent = c.intent.model_copy(
            update={
                "execution_window": window.model_copy(
                    update={
                        "budgets": ActorGenerationBudgets(
                            preparation_seconds=20,
                            execution_seconds=10,
                            retention_seconds=120,
                        )
                    }
                )
            }
        )
    _, authority, _ = bound(c)
    window = c.intent.execution_window
    assert window is not None
    authority.request = ActorRunRequest.model_validate(
        authority.request.model_copy(update={"generation_budgets": window.budgets})
    )
    c.model = RecordedLocalActorModel(
        c.root,
        c.binding,
        c.client,
        c.loop.store,
        c.loop.journal.controls,
        authority,
        clock=clock,
        prepare_control=generation_preparation_control,
    )
    request = ActorDispatch(
        intent=GenerationPlanned(operation=c.event_op, intent=c.intent),
        expected_revision=0,
        result_operation=c.intent.operation.cleanup(
            "window-record-result",
            now=c.intent.operation.deadline,
            seconds=window.budgets.result_ceiling_seconds(15),
        ),
    )
    original = c.intent.model_dump_json()
    put, read = c.loop.store.put, c.loop.store.read
    schemas = {
        "actor-worker-command/1",
        "actor-worker-reply/1",
        "actor-model-response/1",
        "local-actor-execution/1",
    }
    exchanges = []

    def slow_put(raw: bytes, meta: Any, control: Any = None, **kwargs: Any) -> Any:
        if meta.content_schema in schemas:
            exchanges.append(("put", meta.content_schema, control.checkpoint()))
            clock.sleep(9)
        return put(raw, meta, control, **kwargs)

    def slow_read(ref: Any, control: Any = None) -> bytes:
        if ref.content_schema in schemas and control is not None:
            exchanges.append(("read", ref.content_schema, control.checkpoint()))
            clock.sleep(9)
        return read(ref, control)

    monkeypatch.setattr(c.loop.store, "put", slow_put)
    monkeypatch.setattr(c.loop.store, "read", slow_read)
    if selected:
        after = execute_actor_generation(
            request, c.loop.journal, c.model, c.loop.journal.controls, clock=clock
        )
        assert after.project().generation is not None
        assert exchanges[0][2] == 120
        assert all(
            any(x[:2] == (kind, schema) for x in exchanges)
            for schema in schemas
            for kind in ("put", "read")
        )
        assert clock.elapsed >= 72
        assert after.events[-1].operation.deadline <= request.result_operation.deadline
        assert after.events[-1].operation.deadline <= clock.utcnow() + timedelta(
            seconds=15
        )
    else:
        with pytest.raises(ActorDispatchFailure):
            execute_actor_generation(
                request, c.loop.journal, c.model, c.loop.journal.controls, clock=clock
            )
    assert c.loader.session.calls == 1 and c.intent.model_dump_json() == original
    assert len(list(c.root.glob("*.local-actor-call.json"))) == 1


def test_retention_reserve_blocks_new_side_effect_when_actor_time_is_insufficient(
    tmp_path: Path,
) -> None:
    c, clock, _ = window_case(tmp_path)
    request = ActorRunRequest.model_validate(
        c.loop.request.model_copy(
            update={
                "operation": c.loop.request.operation.model_copy(
                    update={"deadline": clock.utcnow() + timedelta(seconds=150)}
                ),
                "generation_budgets": ActorGenerationBudgets(
                    preparation_seconds=20, execution_seconds=10, retention_seconds=120
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
    with pytest.raises(ActorLoopFailure):
        runner.run(request)
    assert c.loader.session.calls == c.loop.browser.calls == 0
    assert not list(c.root.iterdir())


@pytest.mark.parametrize("bad", [0, -1, 601, True, "300", 1.5])
def test_invalid_retention_rejected(bad: Any) -> None:
    with pytest.raises(ValidationError):
        ActorGenerationBudgets(
            preparation_seconds=900, execution_seconds=600, retention_seconds=bad
        )


def test_legacy_budget_canonical_bytes_preserved() -> None:
    raw = '{"schema_version":"actor-generation-budgets/1","preparation_seconds":900,"execution_seconds":600}'
    assert ActorGenerationBudgets.model_validate_json(raw).model_dump_json() == raw
