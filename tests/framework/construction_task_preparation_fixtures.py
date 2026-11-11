"""Current TaskActor2 from one frozen original plan; unit physical/model facts."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.application.construction_task_preparation import (
    ActorPreparationDeps,
)
from lab_generate_skill.bootstrap.construction_control import (
    actor_preparation_dependencies,
    construction_control_dependencies,
    construction_steps,
)
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from lab_generate_skill.domain.construction_task_preparation import ActorPreparation
from lab_generate_skill.ports.construction import ConstructionSteps
from actor_admission_fixtures import fixture as admission_case
from task_actor_v2_fixtures import CurrentTaskCase, current_task_case
from task_execution_fixtures import TaskCase, task_case
from task_teacher_source_fixtures import UnitCompleteTaskAuthority
from test_run_journal import command


@dataclass
class TaskPreparationCase:
    current: CurrentTaskCase
    control: ConstructionDeps
    deps: ActorPreparationDeps
    records: ConstructionSteps

    def request(self, name: str = "first") -> ActorPreparation:
        op = command("prepare-original-actor-" + name)
        progress = self.control.journal.read(op)
        return ActorPreparation(
            run=progress.plan.run,
            expected_revision=progress.revision,
            task=self.current.task.plan,
            operation=op,
            completion_operation=op.cleanup(
                "prepared-original-actor-result-" + name,
                now=datetime.now(timezone.utc),
                seconds=60,
            ),
        )


def task_preparation_case(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> TaskPreparationCase:
    def build(path: Path) -> TaskCase:
        path.mkdir()
        admitted = admission_case(
            path,
            stage="planned",
            allowed_actions=("send_msg_to_user",),
            register_attempt=False,
        )
        return task_case(path, admitted=admitted)

    current = current_task_case(root, monkeypatch, task_builder=build)
    task = current.task
    data = task.admission.data
    authority = UnitCompleteTaskAuthority(data.authority)
    authority.tasks[task.plan.intent.binding.attempt_id] = task
    data.authority = authority
    journal = data.journal()
    task.deps = replace(
        task.deps,
        construction=journal,
        admission=replace(task.deps.admission, construction=journal),
    )
    base = construction_control_dependencies(
        journal,
        task.deps.controls,
        readiness=ConstructionReadiness(
            task.deps.runs,
            data.claims(),
            EvidenceRunPlans(data.store, task.deps.controls),
            authority,
        ),
    )
    control = replace(base, attempts=RecordedConstructionTask(task.plan, task.deps))
    return TaskPreparationCase(
        current,
        control,
        actor_preparation_dependencies(control, evidence=data.store),
        construction_steps(data.store),
    )
