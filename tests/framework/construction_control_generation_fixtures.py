"""Original initial construction, file run/claim/plan and synthetic Generator.

No model/resource/site permission is granted by these unit ports.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.bootstrap.construction_control import (
    construction_control_dependencies,
)
from lab_generate_skill.domain.construction import (
    CallCompleted,
    CallPlanned,
    ConstructionPlan,
    ProgressEvent,
)
from lab_generate_skill.domain.construction_inputs import (
    GeneratedCandidate,
    GenerationInput,
)
from lab_generate_skill.domain.construction_control import (
    ConstructionStepPlan,
    GenerateConstructionWork,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.runtime.lifecycle import OperationGuards
from construction_storage_fixtures import fixture, StorageFixture
from test_run_journal import command, CancelSwitch, Harness


class UnitGenerator:
    def __init__(self, data: StorageFixture, journal: ConstructionJournal) -> None:
        self.data, self.journal = data, journal
        self.calls: list[GenerationInput] = []
        self.error: BaseException | None = None

    def generate(
        self, request: GenerationInput, operation: OperationContext
    ) -> GeneratedCandidate:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        progress = self.journal.read(operation)
        assert progress.project().pending_call is not None
        event = self.data.event(progress)
        assert isinstance(event, CallCompleted)
        assert isinstance(event.response, GeneratedCandidate)
        assert request.request_id == event.response.request_id
        return event.response


class CompletionAcknowledgmentFault:
    """Fail before/after the original completion commit; do not fake its outcome."""

    def __init__(
        self, original: ConstructionJournal, error: BaseException, *, commit_first: bool
    ) -> None:
        self.original, self.error, self.commit_first = original, error, commit_first

    def create(
        self, plan: ConstructionPlan, op: OperationContext
    ) -> ConstructionProgress:
        return self.original.create(plan, op)

    def read(self, op: OperationContext) -> ConstructionProgress:
        return self.original.read(op)

    def append(
        self, event: ProgressEvent, expected_revision: int, op: OperationContext
    ) -> ConstructionProgress:
        if isinstance(event, CallCompleted):
            if self.commit_first:
                self.original.append(event, expected_revision, op)
            raise self.error
        return self.original.append(event, expected_revision, op)


@dataclass
class GenerationCase:
    data: StorageFixture
    deps: ConstructionDeps
    generator: UnitGenerator

    def step(self) -> ConstructionStepPlan:
        current = self.deps.journal.read(command())
        planned = self.data.event(current)
        assert isinstance(planned, CallPlanned)
        request = GenerationInput.model_validate_json(
            self.data.store.read(planned.call.input_ref)
        )
        invoke = command("controlled-generator-invocation")
        return ConstructionStepPlan(
            run=self.data.plan.run,
            expected_revision=current.revision,
            operation=planned.operation,
            work=GenerateConstructionWork(
                planned=planned,
                request=request,
                invoke_operation=invoke,
                completion_operation=invoke.cleanup(
                    "controlled-generator-completed",
                    now=datetime.now(timezone.utc),
                    seconds=60,
                ),
            ),
        )


def generation_case(root: Path) -> GenerationCase:
    root.mkdir()
    data = fixture(root)
    controls = OperationGuards(SystemClock(), CancelSwitch())
    plans = EvidenceRunPlans(data.store, controls)
    run = plans.load(data.plan.run, command())
    run_root = root / "control-run-journal"
    run_root.mkdir()
    runs = FileRunJournal(
        run_root, data.plan.run, controls, data.store, capacity=run.run_capacity
    )
    harness = Harness(
        run_root,
        data.store,
        runs,
        data.plan.run,
        data.plan.claim_ref,
        CancelSwitch(),
        run.run_capacity,
    )
    harness.running()
    journal = data.journal()
    journal.create(data.plan, command("control-create"))
    generator = UnitGenerator(data, journal)
    deps = construction_control_dependencies(
        journal,
        controls,
        readiness=ConstructionReadiness(runs, data.claims(), plans, data.authority),
    )
    return GenerationCase(
        data, replace(deps, evidence=data.store, generator=generator), generator
    )
