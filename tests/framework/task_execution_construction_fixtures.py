"""Original construction journal consuming the new concrete task result variant.

All physical permissions remain unit facts. Actual file logs and native receipt
bytes are verified; this is not a production source/closure authority default.
"""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from lab_generate_skill.adapters.ledger.construction_journal import (
    FileConstructionJournal,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.bootstrap.construction_control import (
    construction_control_dependencies,
)
from lab_generate_skill.bootstrap.task_execution import RecordedConstructionTask
from lab_generate_skill.domain.construction import (
    ConstructionPlan,
    ProgressEvent,
    AttemptCompleted,
)
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction_control import (
    ConstructionStepPlan,
    ExecuteConstructionWork,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.task_execution import ClosedTaskResources
from task_execution_fixtures import TaskCase, task_case
from construction_storage_fixtures import limits
from test_construction_state import planned_attempt
from test_run_journal import command


class UnitExecutedTaskAuthority:
    def __init__(self, case: TaskCase) -> None:
        self.case = case

    def verify_plan(self, plan: ConstructionPlan, op: OperationContext) -> None:
        self.case.admission.data.authority.verify_plan(plan, op)

    def verify_event(
        self, progress: ConstructionProgress, event: ProgressEvent, op: OperationContext
    ) -> None:
        c = self.case
        d = c.admission.data
        if not isinstance(event, AttemptCompleted):
            d.authority.verify_event(progress, event, op)
            return
        result = event.result
        envelope = TaskAttemptResult.model_validate_json(
            d.store.read(result.attempt_ref)
        )
        native = ExecutedTaskReceipt.model_validate_json(
            d.store.read(envelope.execution_ref)
        )
        trace = InteractionTrace.model_validate_json(d.store.read(native.trace_ref))
        closed = ClosedTaskResources.model_validate_json(
            d.store.read(native.closed_ref)
        )
        reset = c.deps.states.load_reset(native.reset_ref, op)
        assert (
            native.intent
            == envelope.intent
            == result.intent
            == progress.project().pending_attempt
        )
        assert (
            native.evaluation_ref == result.evaluation_ref
            and reset.status == "safe"
            and reset.closure_refs == closed.closure_refs
        )
        assert (
            (trace.generations, trace.interactions)
            == (native.generations, native.interactions)
            == (result.generations, result.interactions)
        )
        assert (envelope.generations, envelope.interactions) == (
            result.generations,
            result.interactions,
        )
        run, attempts = c.deps.runs.read(op).project()
        actual = next(a for a in attempts if a.binding == result.intent.binding)
        assert run.stage == "running" and actual.stage == "sealed"
        assert native.reset_ref in actual.events[-1].outputs
        assert native.plan_ref.content_schema == "task-execution-plan/1"


def construction_task_case(
    root: Path,
) -> tuple[TaskCase, ConstructionStepPlan, ConstructionDeps]:
    c = task_case(root)
    d = c.admission.data
    controls = c.deps.controls
    journal_root = root / "native-result-construction"
    journal_root.mkdir()
    authority = UnitExecutedTaskAuthority(c)
    journal = FileConstructionJournal(
        journal_root,
        d.plan,
        limits(),
        controls,
        d.store,
        EvidenceRunPlans(d.store, controls),
        authority,
        EvidenceContextRecords(d.store, controls, d.context_authority),
        EvidenceRetrievalRecords(d.store, controls, d.retrieval_authority),
        d.claims(),
    )
    progress = journal.create(d.plan, command("task-native-construction-create"))
    while progress.project().next_action.kind != "execute":
        event = d.event(progress)
        progress = journal.append(event, progress.revision, event.operation)
    planned = planned_attempt(progress)
    assert planned.intent == c.plan.intent
    c.deps = replace(
        c.deps,
        construction=journal,
        admission=replace(c.deps.admission, construction=journal),
    )
    deps = construction_control_dependencies(
        journal,
        controls,
        readiness=ConstructionReadiness(
            c.deps.runs, d.claims(), EvidenceRunPlans(d.store, controls), authority
        ),
    )
    deps = replace(deps, attempts=RecordedConstructionTask(c.plan, c.deps))
    step = ConstructionStepPlan(
        run=d.plan.run,
        expected_revision=progress.revision,
        operation=planned.operation,
        work=ExecuteConstructionWork(
            planned=planned,
            invoke_operation=c.plan.operation,
            completion_operation=planned.operation.cleanup(
                "task-native-construction-completed",
                now=datetime.now(timezone.utc),
                seconds=60,
            ),
        ),
    )
    return c, step, deps
