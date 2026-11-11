"""Actual resource/CAS/RunPlan/RunJournal, explicit engineering lower authority."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.application.generator_resource_admission import (
    RunGeneratorResourceAuthority,
    GeneratorResourceAdmissionDeps,
)
from lab_generate_skill.domain.execution import RunBinding, RunStage
from lab_generate_skill.domain.generator_model_binding import GeneratorModelBinding
from lab_generate_skill.domain.run_plan import RunPlan
from generator_resource_fixtures import ResourceCase
from test_evidence_run_plans import persisted_plan
from test_run_journal import Harness, CancelSwitch, command


@dataclass
class AdmissionCase:
    resource: ResourceCase
    run: RunBinding
    plan: RunPlan
    harness: Harness
    deps: GeneratorResourceAdmissionDeps
    authority: RunGeneratorResourceAuthority

    def stop(self) -> None:
        snapshot = self.harness.journal.read(command())
        entry = self.harness.run_entry(snapshot, "closing", "cancelled")
        self.harness.journal.append(entry, snapshot.revision, entry.event.operation)


def admission_case(
    c: ResourceCase,
    root: Path,
    *,
    stage: RunStage = "running",
    change: Callable[[RunPlan], RunPlan] | None = None,
) -> AdmissionCase:
    plan = persisted_plan(c.evidence)
    model = GeneratorModelBinding.model_validate_json(
        c.evidence.read(c.spec.model_binding_ref)
    )
    plan = plan.model_copy(
        update={
            "release_ref": c.spec.release_ref,
            "purpose": "engineering",
            "models": tuple(
                (
                    m.model_copy(
                        update={
                            "provider": "transformers",
                            "model": model.model,
                            "model_binding_ref": c.spec.model_binding_ref,
                        }
                    )
                    if m.role == "generator"
                    else m
                )
                for m in plan.models
            ),
        }
    )
    if change is not None:
        plan = change(plan)
    plans = EvidenceRunPlans(c.evidence, c.controls)
    reference = plans.publish(plan, command("publish"))
    run = RunBinding(
        owner=c.spec.token.owner,
        plan_ref=reference,
        release_ref=plan.release_ref,
        submission_key="engineering-submission",
    )
    root.mkdir()
    journal = FileRunJournal(
        root, run, c.controls, c.evidence, capacity=plan.run_capacity
    )
    harness = Harness(
        root, c.evidence, journal, run, run.plan_ref, CancelSwitch(), plan.run_capacity
    )
    snapshot = harness.create()
    stages: tuple[RunStage, ...] = (
        "validated",
        "claimed",
        "submitting",
        "submitted",
        "running",
    )
    for next_stage in stages:
        if snapshot.project()[0].stage == stage:
            break
        entry = harness.run_entry(snapshot, next_stage)
        snapshot = journal.append(entry, snapshot.revision, entry.event.operation)
    deps = GeneratorResourceAdmissionDeps(plans, journal, c.evidence, c.authority)
    return AdmissionCase(
        c, run, plan, harness, deps, RunGeneratorResourceAuthority(run, deps)
    )
