"""One current pending-task gate shared by preparation and initialization."""

from collections.abc import Callable
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task_phase_source import TaskPhaseSourceState
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.task_phase_source import (
    TaskPhaseSources,
    TaskPhaseResourceAuthority,
    TaskPhaseResourceReads,
    TaskPhaseResourceRechecks,
)
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from .context_evidence import read_bytes


class TaskStateAdmission:
    def __init__(
        self,
        sources: TaskPhaseSources,
        runs: RunJournal,
        authority: TaskPhaseResourceAuthority,
        evidence: EvidenceStore,
    ) -> None:
        if any(x is None for x in (sources, runs, authority, evidence)):
            raise ValueError(
                "Original journals and physical/source authority are mandatory"
            )
        self.sources, self.runs, self.authority, self.evidence = (
            sources,
            runs,
            authority,
            evidence,
        )

    def verify(
        self,
        plan: TaskExecutionPlan,
        scope: StateScope,
        operation: OperationContext,
        control: OperationControl,
        *,
        stages: tuple[str, ...],
        cleanup_parents: tuple[str, ...],
        proof: Callable[[TaskPhaseSourceState, RunSnapshot, ResetPlan], None],
        reset_input: ResetPlan | None = None,
    ) -> None:
        plan = TaskExecutionPlan.model_validate(plan)
        operation = OperationContext.model_validate(operation)
        control.checkpoint()
        loaded = (
            self.authority.read_for_admission(
                plan, plan.read_operation, control, sources=self.sources
            )
            if isinstance(self.authority, TaskPhaseResourceReads)
            else None
        )
        try:
            progress = (
                loaded.state
                if loaded is not None
                else self.sources.read(plan, plan.read_operation, control)
            )
            snapshot = self.runs.read(plan.read_operation)
            run, attempts = snapshot.project()
            original = [
                attempt
                for attempt in attempts
                if attempt.binding == plan.intent.binding
            ]
            if (
                snapshot.binding != plan.intent.binding.run
                or progress.intent.binding.run != snapshot.binding
                or progress.intent != plan.intent
                or run.stage != "running"
                or run.stop_reason is not None
                or len(original) != 1
            ):
                raise OwnershipConflict(
                    "Task needs the exact original live pending attempt"
                )
            if operation.mode == "execute" and original[0].stage not in stages:
                raise OwnershipConflict(
                    "Task effects require original " + "/".join(stages) + " stage"
                )
            if (
                operation.mode == "cleanup"
                and operation.parent_operation_id not in cleanup_parents
            ):
                raise OwnershipConflict(
                    "Read-only task facts require linked original provenance"
                )
            if (operation.run_id, operation.owner_id, operation.attempt_id) != (
                scope.owner.run_id,
                scope.owner.owner_id,
                scope.attempt_id,
            ):
                raise OwnershipConflict(
                    "Task admission changed original operation scope"
                )
            reset = (
                ResetPlan.model_validate_json(
                    read_bytes(self.evidence, plan.reset_plan_ref, 2 * 1024**2, control)
                )
                if reset_input is None
                else ResetPlan.model_validate(reset_input)
            )
            if reset_input is not None:
                if (
                    plan.reset_plan_ref.content_schema,
                    plan.reset_plan_ref.visibility,
                ) != (reset.schema_version, "private"):
                    raise OwnershipConflict(
                        "Reset input changed original schema/visibility"
                    )
                require_complete_bytes(
                    plan.reset_plan_ref, reset.model_dump_json().encode()
                )
            proof(progress, snapshot, reset)
            if loaded is None:
                self.authority.verify(
                    plan, progress, snapshot, reset, plan.read_operation, control
                )
            else:
                loaded.verify(snapshot, reset, control)
            if (
                loaded.recheck(control)
                if isinstance(loaded, TaskPhaseResourceRechecks)
                else self.sources.read(plan, plan.read_operation, control)
            ) != progress or self.runs.read(plan.read_operation) != snapshot:
                raise RevisionConflict(
                    "Original task journals changed during admission"
                )
            control.checkpoint()
        finally:
            if loaded is not None:
                loaded.close()
