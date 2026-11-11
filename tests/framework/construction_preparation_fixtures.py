"""Actual original CAS/journals/Generator role; explicit synthetic native engine."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.application.construction_preparation import (
    GenerationPreparationDeps,
)
from lab_generate_skill.bootstrap.construction_control import (
    construction_control_dependencies,
    generation_preparation_dependencies,
    construction_steps,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.domain.construction_preparation import GeneratorPreparation
from lab_generate_skill.ports.construction import ConstructionSteps
from generator_admission_fixtures import Case, case
from test_run_journal import command


@dataclass
class PreparationCase:
    native: Case
    control: ConstructionDeps
    deps: GenerationPreparationDeps
    records: ConstructionSteps

    def request(self, name: str = "first") -> GeneratorPreparation:
        c = self.native
        op = command("prepare-generator-" + name)
        invoke = command("prepared-inference-" + name)
        return GeneratorPreparation(
            run=c.data.plan.run,
            expected_revision=c.deps.construction.read(op).revision,
            request_id="prepared-generator-" + name,
            operation=op,
            invoke_operation=invoke,
            completion_operation=invoke.cleanup(
                "prepared-completion-" + name,
                now=datetime.now(timezone.utc),
                seconds=60,
            ),
        )


def preparation_case(root: Path) -> PreparationCase:
    root.mkdir()
    c = case(root, planned=False)
    plans = EvidenceRunPlans(c.data.store, c.controls)
    control = construction_control_dependencies(
        c.deps.construction,
        c.controls,
        readiness=ConstructionReadiness(
            c.deps.runs, c.data.claims(), plans, c.data.authority
        ),
    )
    control = replace(control, evidence=c.data.store, generator=c.role)
    deps = generation_preparation_dependencies(
        control,
        evidence=c.data.store,
        retrieval=EvidenceRetrievalRecords(
            c.data.store, c.controls, c.data.retrieval_authority
        ),
    )
    return PreparationCase(c, control, deps, construction_steps(c.data.store))
