"""Real journal/once gate and resident synthetic worker with one controllable clock."""

from lab_generate_skill.application.actor_generation_control import (
    generation_preparation_control,
)

from datetime import datetime, timedelta, timezone
from pathlib import Path

from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.domain.actor_dispatch import ActorDispatch
from lab_generate_skill.domain.actor_execution_window import (
    ActorGenerationBudgets,
    ActorGenerationWindow,
)
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.trace_events import GenerationIntent, GenerationPlanned
from lab_generate_skill.runtime.lifecycle import OperationGuards
from local_actor_fixtures import Case, case
from test_lifecycle import CancelSwitch, ManualClock


def window_case(root: Path) -> tuple[Case, ManualClock, CancelSwitch]:
    c = case(root)
    clock, cancel = ManualClock(), CancelSwitch()
    clock.wall = datetime.now(timezone.utc)
    controls = OperationGuards(clock, cancel)
    c.loop.journal.controls = controls
    window = ActorGenerationWindow(
        budgets=ActorGenerationBudgets(preparation_seconds=20, execution_seconds=10),
        prepared_at=clock.utcnow(),
    )
    op = c.intent.operation.model_copy(
        update={
            "deadline": clock.utcnow() + timedelta(seconds=30),
            "parent_operation_id": c.loop.request.operation.operation_id,
            "cancellation_ref": CancellationRef(
                channel_id="window-control",
                run_id=c.intent.operation.run_id,
                owner_id=c.intent.operation.owner_id,
            ),
        }
    )
    c.intent = GenerationIntent.model_validate(
        c.intent.model_copy(
            update={
                "operation": op,
                "execution_window": window,
            }
        )
    )
    c.model = new_model(c, clock)
    return c, clock, cancel


def new_model(c: Case, clock: ManualClock) -> RecordedLocalActorModel:
    return RecordedLocalActorModel(
        c.root,
        c.binding,
        c.client,
        c.loop.store,
        c.loop.journal.controls,
        c.authority,
        clock=clock,
        prepare_control=generation_preparation_control,
    )


def dispatch(c: Case) -> ActorDispatch:
    return ActorDispatch(
        intent=GenerationPlanned(operation=c.event_op, intent=c.intent),
        expected_revision=0,
        result_operation=c.intent.operation.cleanup(
            "window-record-result",
            now=c.intent.operation.deadline,
            seconds=15,
        ),
    )
