"""Four real current task entries on one original file history; native effects unit.

Reuses the existing full-method task/Actor2 fixtures. This is a shared interface
test, not another website group, actual source request or four Map deployments.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.bootstrap.construction_task_execution import (
    RecordedConstructionTasks,
)
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from lab_generate_skill.domain.construction import AttemptCompleted, AttemptIntent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.adapters.ledger.construction_journal import (
    FileConstructionJournal,
)
from actor_admission_fixtures import fixture as admission_case
from construction_storage_fixtures import StorageFixture
from source_actor_context_fixtures import source_context_case
from actor_long_fixtures import long_config
from task_actor_v2_fixtures import current_task_case, CurrentTaskCase
from task_execution_fixtures import task_case, TaskCase
from task_teacher_source_fixtures import UnitCompleteTaskAuthority
from test_run_journal import command
from test_slurm_commands import guard


@dataclass
class MultiTaskFactoryCase:
    tasks: tuple[CurrentTaskCase, ...]
    native: Any
    port: RecordedConstructionTasks
    calls: tuple[AttemptIntent, ...]
    data: StorageFixture


@contextmanager
def four_current_tasks(
    root: Path, patch: pytest.MonkeyPatch
) -> Iterator[MultiTaskFactoryCase]:
    root.mkdir()
    native = source_context_case(
        root / "shared-native64", patch, engine_config=long_config()
    )
    tasks: list[CurrentTaskCase] = []
    prepared: dict[str, RecordedConstructionTask] = {}
    calls: list[AttemptIntent] = []
    prepared_cases: dict[str, CurrentTaskCase] = {}
    data: StorageFixture | None = None
    port: RecordedConstructionTasks | None = None
    authority: UnitCompleteTaskAuthority | None = None
    read: OperationContext | None = None
    shared_claims: SourceClaims | None = None
    journal: FileConstructionJournal | None = None

    def factory(
        intent: AttemptIntent, op: OperationContext, control: OperationControl
    ) -> RecordedConstructionTask:
        control.checkpoint()
        selected = prepared[intent.binding.attempt_id]
        assert selected.plan.intent == intent and selected.plan.operation == op
        assert (
            "acquire" not in prepared_cases[intent.binding.attempt_id].task.phases.calls
        )
        calls.append(intent)
        return selected

    try:
        for slot in range(4):

            def build(path: Path) -> TaskCase:
                nonlocal data, authority, journal, shared_claims, read, port
                if data is None:
                    c = task_case(path)
                    data = c.admission.data
                    authority = UnitCompleteTaskAuthority(data.authority)
                    data.authority = authority
                    journal = data.journal()
                    shared_claims = c.deps.admission.claims
                    # Batch read lifetime selected before any task effects or
                    # Actor binding; per-task execution deadlines stay intact.
                    read = c.plan.read_operation.model_copy(
                        update={
                            "operation_id": "original-four-task-read",
                            "deadline": datetime.now(timezone.utc)
                            + timedelta(seconds=240),
                        }
                    )
                    d = ConstructionDeps(
                        journal,
                        c.deps.controls,
                        readiness=ConstructionReadiness(
                            c.deps.runs,
                            shared_claims,
                            EvidenceRunPlans(c.deps.evidence, c.deps.controls),
                            authority,
                        ),
                        evidence=c.deps.evidence,
                    )
                    port = RecordedConstructionTasks(d, read, journal, factory)
                else:
                    path.mkdir()
                    admitted = admission_case(
                        path,
                        stage="planned",
                        allowed_actions=("send_msg_to_user",),
                        shared_data=data,
                    )
                    c = task_case(path, admitted=admitted, shared_run=tasks[0].task)
                assert (
                    journal is not None
                    and read is not None
                    and shared_claims is not None
                )
                c.plan = c.plan.model_copy(update={"read_operation": read})
                c.deps = replace(
                    c.deps,
                    construction=journal,
                    admission=replace(
                        c.deps.admission, construction=journal, claims=shared_claims
                    ),
                )
                return c

            current = current_task_case(
                root / ("candidate-" + str(slot)),
                patch,
                shared_native=native,
                task_builder=build,
            )
            c = current.task
            assert (
                authority is not None
                and journal is not None
                and read is not None
                and port is not None
            )
            assert (
                c.plan.intent.candidate_slot == slot and current.binding.plan == c.plan
            )
            prepared_cases[c.plan.intent.binding.attempt_id] = current
            authority.tasks[c.plan.intent.binding.attempt_id] = c
            prepared[c.plan.intent.binding.attempt_id] = RecordedConstructionTask(
                c.plan, c.deps
            )
            result = port.execute(c.plan.intent, c.plan.operation)
            snapshot = journal.read(read)
            event = AttemptCompleted(
                operation=command("original-factory-complete-" + str(slot)),
                result=result,
            )
            journal.append(event, snapshot.revision, event.operation)
            tasks.append(current)
        assert data is not None and port is not None
        yield MultiTaskFactoryCase(tuple(tasks), native, port, tuple(calls), data)
    finally:
        native.client.close(guard(30))
