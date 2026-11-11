"""Current original source/readiness and task entry; explicit synthetic native facts."""

from dataclasses import replace
from pathlib import Path
from lab_generate_skill.adapters.ledger.construction_journal import (
    FileConstructionJournal,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from task_execution_fixtures import task_case, TaskCase


def original_factory_case(
    root: Path,
) -> tuple[TaskCase, ConstructionDeps, RecordedConstructionTask]:
    c = task_case(root)
    assert isinstance(c.deps.construction, FileConstructionJournal)
    # The current composition uses the same original handles. The old generic
    # fixture opens a second read view; narrow it to the actual current handle
    # without changing any persisted source/run/claim facts.
    c.deps = replace(
        c.deps, admission=replace(c.deps.admission, construction=c.deps.construction)
    )
    d = ConstructionDeps(
        c.deps.construction,
        c.deps.controls,
        readiness=ConstructionReadiness(
            c.deps.runs,
            c.deps.admission.claims,
            EvidenceRunPlans(c.deps.evidence, c.deps.controls),
            c.admission.data.authority,
        ),
        evidence=c.deps.evidence,
    )
    return c, d, RecordedConstructionTask(c.plan, c.deps)
