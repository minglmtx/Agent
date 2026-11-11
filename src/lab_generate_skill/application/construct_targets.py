"""One bounded advance of the original construction state machine.

No alternative method, runner, ledger, model retry or environment lifecycle.
The caller supplies frozen inputs; original role/lifecycle ports own execution.
An existing pending/unknown operation is observed, never invoked by this entry.
Known returned facts use record-only work even after execution eligibility ends.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from lab_generate_skill.domain.construction import (
    ConstructionPlan,
    CallCompleted,
    AttemptCompleted,
    SelectionCommitted,
    ProgressEvent,
    ConstructionAttemptResult,
)
from lab_generate_skill.domain.construction_inputs import (
    GeneratedCandidate,
    RevisionResult,
)
from lab_generate_skill.domain.construction_state import (
    ConstructionProgress,
    select_target,
)
from lab_generate_skill.domain.construction_control import (
    ConstructionStepPlan,
    ConstructionResult,
    GenerateConstructionWork,
    ReviseConstructionWork,
    ExecuteConstructionWork,
    RecordConstructionWork,
    ObserveConstructionWork,
)
from lab_generate_skill.domain.teacher_assembly import PublishedTeacherRevisionAssembly
from lab_generate_skill.domain.claims import check_source_claim
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    RevisionConflict,
)
from lab_generate_skill.ports.construction import (
    ConstructionJournal,
    ConstructionAuthority,
)
from lab_generate_skill.ports.construction_execution import ConstructionAttemptExecution
from lab_generate_skill.ports.generation import Generator
from lab_generate_skill.ports.teacher import Teacher
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.run_plan import RunPlans
from lab_generate_skill.ports.claims import SourceClaims
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.domain.lifecycle import OperationContext
from .context_evidence import read_bytes
from .teacher_assembly import TeacherAssemblyDeps, assemble_teacher_revision


@dataclass(frozen=True)
class ConstructionReadiness:
    runs: RunJournal
    claims: SourceClaims
    plans: RunPlans
    original: ConstructionAuthority


@dataclass(frozen=True)
class ConstructionDeps:
    journal: ConstructionJournal
    controls: OperationControls
    readiness: ConstructionReadiness | None = None
    evidence: EvidenceReader | None = None
    generator: Generator | None = None
    attempts: ConstructionAttemptExecution | None = None
    teacher_assembly: TeacherAssemblyDeps | None = None
    teacher_factory: Callable[[PublishedTeacherRevisionAssembly], Teacher] | None = None
    teacher_journal: (
        Callable[[PublishedTeacherRevisionAssembly], ConstructionJournal] | None
    ) = None


class ConstructionStepUnconfirmed(RuntimeError):
    def __init__(
        self,
        step: ConstructionStepPlan,
        phase: str,
        primary: BaseException,
        progress: ConstructionProgress,
        response: (
            GeneratedCandidate | RevisionResult | ConstructionAttemptResult | None
        ),
        teacher: PublishedTeacherRevisionAssembly | None,
        event: ProgressEvent | None,
    ) -> None:
        self.step, self.phase, self.primary = step, phase, primary
        self.progress, self.response, self.teacher, self.event = (
            progress,
            response,
            teacher,
            event,
        )
        super().__init__(
            "Original construction step unresolved; inspect/reconcile saved facts, never reinvoke pending work"
        )


def _result(
    progress: ConstructionProgress,
    *,
    advanced: bool,
    teacher: PublishedTeacherRevisionAssembly | None = None,
) -> ConstructionResult:
    action = progress.project().next_action.kind
    status: Literal["advanced", "waiting", "complete", "observed"] = (
        "complete"
        if action == "complete"
        else (
            "advanced"
            if advanced
            else (
                "waiting"
                if action in ("await_response", "await_attempt", "blocked")
                else "observed"
            )
        )
    )
    return ConstructionResult(status=status, progress=progress, teacher=teacher)


def verify_ready_construction(
    progress: ConstructionProgress,
    deps: ConstructionDeps,
    operation: OperationContext,
    control: OperationControl,
) -> None:
    """The same original live run/claim gate for preparation and dispatch."""
    operation = OperationContext.model_validate(operation)
    binding = progress.plan.run
    if (
        operation.run_id,
        operation.owner_id,
        operation.attempt_id,
        operation.allocation_id,
        operation.recovery_ref,
        operation.mode,
    ) != (binding.owner.run_id, binding.owner.owner_id, None, None, None, "execute"):
        raise OwnershipConflict(
            "New construction work needs original run-level execute scope"
        )
    ready = deps.readiness
    if ready is None:
        raise ValueError(
            "Original construction run/claim/admission dependencies required"
        )
    control.checkpoint()
    ready.original.verify_plan(progress.plan, operation)
    snapshot = RunSnapshot.model_validate(ready.runs.read(operation))
    run, _ = snapshot.project()
    if (
        snapshot.binding != binding
        or run.stage != "running"
        or run.stop_reason is not None
    ):
        raise InvalidTransition(
            "New construction work requires original unstopped running run"
        )
    loaded = ready.plans.load(binding, operation)
    expected = ConstructionPlan.from_run_plan(
        loaded,
        binding,
        progress.plan.task.identity.task_id,
        claim_ref=progress.plan.claim_ref,
        public_context_ref=progress.plan.public_context_ref,
        context_receipt_ref=progress.plan.context_receipt_ref,
        retrieval_ref=progress.plan.retrieval_ref,
        retrieval_scope=progress.plan.retrieval_scope,
        actor_context_configuration_ref=progress.plan.actor_context_configuration_ref,
    )
    if expected != progress.plan:
        raise OwnershipConflict(
            "Control step changed full original frozen construction plan"
        )
    claim = ready.claims.require_source(
        progress.plan.claim_ref, binding, progress.plan.task, operation
    )
    check_source_claim(claim, progress.plan.claim_ref, binding, progress.plan.task)
    control.checkpoint()
    if (
        deps.journal.read(operation) != progress
        or ready.runs.read(operation) != snapshot
    ):
        raise RevisionConflict(
            "Original journals changed during construction admission"
        )
    control.checkpoint()


def construct_targets(
    step: ConstructionStepPlan, deps: ConstructionDeps
) -> ConstructionResult:
    """Advance explicit ready work once, or return current waiting/complete state.

    The outer original queue supplies the next qualified command. This does not
    initialize resources, generate work IDs, infer missing configs or retry roles.
    """
    step = ConstructionStepPlan.model_validate(step)
    if deps.journal is None or deps.controls is None:
        raise ValueError("Original construction journal and controls required")
    control = deps.controls.bind(step.operation)
    control.checkpoint()
    progress = ConstructionProgress.model_validate(deps.journal.read(step.operation))
    if progress.plan.run != step.run:
        raise OwnershipConflict(
            "Control step differs from complete original run binding"
        )
    work = step.work
    if isinstance(work, ObserveConstructionWork):
        return _result(progress, advanced=False)
    # Returned facts are not new execution; retain original authority at append.
    if isinstance(work, RecordConstructionWork):
        journal = deps.journal
        if work.teacher is not None:
            if deps.teacher_journal is None:
                raise ValueError("Original bound Teacher completion proof required")
            journal = deps.teacher_journal(work.teacher)
            if journal.read(step.operation) != progress:
                raise OwnershipConflict(
                    "Teacher fact binder changed original journal history"
                )
        try:
            committed = journal.append(
                work.event, step.expected_revision, step.operation
            )
        except BaseException as error:
            raise ConstructionStepUnconfirmed(
                step,
                "record_original_fact",
                error,
                progress,
                None,
                work.teacher,
                work.event,
            ) from error
        return _result(committed, advanced=True, teacher=work.teacher)
    action = progress.project().next_action.kind
    if action in ("await_response", "await_attempt", "blocked", "complete"):
        return _result(progress, advanced=False)
    if progress.revision != step.expected_revision:
        raise RevisionConflict("Original construction command revision is stale")
    if action != work.kind:
        raise InvalidTransition("Explicit command does not match original next action")
    if isinstance(work, GenerateConstructionWork) and (
        deps.generator is None or deps.evidence is None
    ):
        raise ValueError("Original Generator and exact public input reader required")
    if isinstance(work, ExecuteConstructionWork) and deps.attempts is None:
        raise ValueError("Original complete Actor task lifecycle required")
    if isinstance(work, ReviseConstructionWork) and any(
        value is None
        for value in (deps.teacher_assembly, deps.teacher_factory, deps.teacher_journal)
    ):
        raise ValueError(
            "Original Teacher source/assembly/port/completion proof bindings required"
        )
    if isinstance(
        work,
        (GenerateConstructionWork, ReviseConstructionWork, ExecuteConstructionWork),
    ):
        deps.controls.bind(work.completion_operation).checkpoint()
    verify_ready_construction(progress, deps, step.operation, control)
    phase = "original_registration"
    response: GeneratedCandidate | RevisionResult | ConstructionAttemptResult | None = (
        None
    )
    teacher: PublishedTeacherRevisionAssembly | None = None
    event: ProgressEvent | None = None
    try:
        if isinstance(work, GenerateConstructionWork):
            assert deps.evidence is not None and deps.generator is not None
            if (
                read_bytes(
                    deps.evidence, work.planned.call.input_ref, 4 * 1024**2, control
                )
                != work.request.model_dump_json().encode()
            ):
                raise OwnershipConflict(
                    "Generator command differs from original registered public bytes"
                )
            event = work.planned
            progress = deps.journal.append(event, progress.revision, step.operation)
            verify_ready_construction(progress, deps, step.operation, control)
            phase = "original_generator"
            deps.controls.bind(work.invoke_operation).checkpoint()
            response = GeneratedCandidate.model_validate(
                deps.generator.generate(work.request, work.invoke_operation)
            )
            event = CallCompleted(
                operation=work.completion_operation, response=response
            )
        elif isinstance(work, ExecuteConstructionWork):
            assert deps.attempts is not None
            event = work.planned
            progress = deps.journal.append(event, progress.revision, step.operation)
            verify_ready_construction(progress, deps, step.operation, control)
            phase = "original_actor_lifecycle"
            deps.controls.bind(work.invoke_operation).checkpoint()
            response = ConstructionAttemptResult.model_validate(
                deps.attempts.execute(work.planned.intent, work.invoke_operation)
            )
            if response.intent != work.planned.intent:
                raise OwnershipConflict(
                    "Actor lifecycle returned another original attempt"
                )
            event = AttemptCompleted(
                operation=work.completion_operation, result=response
            )
        elif isinstance(work, ReviseConstructionWork):
            assert (
                deps.teacher_assembly is not None
                and deps.teacher_factory is not None
                and deps.teacher_journal is not None
            )
            if deps.teacher_assembly.journal.read(step.operation) != progress:
                raise OwnershipConflict("Teacher assembly changed original journal")
            teacher = assemble_teacher_revision(
                work.original, deps.teacher_assembly, control=control
            )
            progress = deps.journal.read(step.operation)
            phase = "bind_original_teacher"
            role = deps.teacher_factory(teacher)
            journal = deps.teacher_journal(teacher)
            if journal.read(step.operation) != progress:
                raise OwnershipConflict(
                    "Teacher proof binder changed original journal history"
                )
            verify_ready_construction(progress, deps, step.operation, control)
            phase = "original_teacher"
            response = RevisionResult.model_validate(
                role.revise(teacher.bound.plan.revision, step.operation)
            )
            if response.schema_version != "revision-result/2":
                raise OwnershipConflict(
                    "New controlled Teacher step requires original v2 execution proof"
                )
            event = CallCompleted(
                operation=work.completion_operation, response=response
            )
            phase = "complete_original_teacher"
            committed = journal.append(
                event, progress.revision, work.completion_operation
            )
            return _result(committed, advanced=True, teacher=teacher)
        else:
            event = SelectionCommitted(
                operation=step.operation,
                selection=select_target(progress.project().attempts),
            )
            return _result(
                deps.journal.append(event, progress.revision, step.operation),
                advanced=True,
            )
        phase = "complete_original_execution"
        # Completion gets its own bounded context; never renew the send operation.
        committed = deps.journal.append(event, progress.revision, event.operation)
        return _result(committed, advanced=True)
    except BaseException as error:
        raise ConstructionStepUnconfirmed(
            step, phase, error, progress, response, teacher, event
        ) from error
