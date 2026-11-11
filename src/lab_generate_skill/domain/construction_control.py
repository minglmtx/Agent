"""One explicit original construction step, not a model retry/resume permit.

The existing ConstructionProgress owns the method/schedule. Commands supply
frozen role inputs/operations; a pending call/attempt is never invoked again.
Known facts have a separate append-only command, including after run stop.
"""

from typing import Annotated, Literal, Self
from pydantic import Field, model_validator
from .construction import (
    CallPlanned,
    AttemptPlanned,
    CallCompleted,
    CallUncertain,
    AttemptCompleted,
    AttemptResolved,
)
from .construction_inputs import GenerationInput, RevisionResult
from .construction_state import ConstructionProgress
from .execution import RunBinding
from .lifecycle import OperationContext
from .teacher_assembly import (
    TeacherRevisionAssemblyInput,
    PublishedTeacherRevisionAssembly,
)
from .validation import Contract


class GenerateConstructionWork(Contract):
    kind: Literal["generate"] = "generate"
    planned: CallPlanned
    request: GenerationInput
    invoke_operation: OperationContext
    completion_operation: OperationContext


class ReviseConstructionWork(Contract):
    kind: Literal["revise"] = "revise"
    original: TeacherRevisionAssemblyInput
    completion_operation: OperationContext


class ExecuteConstructionWork(Contract):
    kind: Literal["execute"] = "execute"
    planned: AttemptPlanned
    invoke_operation: OperationContext
    completion_operation: OperationContext


class RecordConstructionWork(Contract):
    kind: Literal["record"] = "record"
    event: Annotated[
        CallCompleted | CallUncertain | AttemptCompleted | AttemptResolved,
        Field(discriminator="kind"),
    ]
    teacher: PublishedTeacherRevisionAssembly | None = None

    @model_validator(mode="after")
    def known_teacher_binding(self) -> Self:
        needs = (
            isinstance(self.event, CallCompleted)
            and isinstance(self.event.response, RevisionResult)
            and self.event.response.schema_version == "revision-result/2"
        )
        if needs != (self.teacher is not None):
            raise ValueError(
                "Teacher v2 record requires its explicit original assembly, no inferred lookup"
            )
        if self.teacher is not None and isinstance(self.event, CallCompleted):
            if (
                self.event.response.request_id
                != self.teacher.bound.plan.revision.request_id
            ):
                raise ValueError("Known result changed original Teacher assembly")
        return self


class SelectConstructionWork(Contract):
    kind: Literal["select"] = "select"


class ObserveConstructionWork(Contract):
    kind: Literal["observe"] = "observe"


ConstructionWork = Annotated[
    GenerateConstructionWork
    | ReviseConstructionWork
    | ExecuteConstructionWork
    | RecordConstructionWork
    | SelectConstructionWork
    | ObserveConstructionWork,
    Field(discriminator="kind"),
]


class ConstructionStepPlan(Contract):
    schema_version: Literal["construction-step-plan/1"] = "construction-step-plan/1"
    run: RunBinding
    expected_revision: int = Field(ge=-1, le=255)
    operation: OperationContext
    work: ConstructionWork

    @model_validator(mode="after")
    def original_operations_and_inputs(self) -> Self:
        owner, op, work = self.run.owner, self.operation, self.work

        def run_level(value: OperationContext) -> None:
            if (
                value.run_id,
                value.owner_id,
                value.attempt_id,
                value.allocation_id,
                value.recovery_ref,
            ) != (owner.run_id, owner.owner_id, None, None, None):
                raise ValueError("Construction control needs original run-level scope")

        run_level(op)
        if isinstance(work, (RecordConstructionWork,)):
            if work.event.operation != op and not (
                op.mode == "cleanup"
                and op.parent_operation_id == work.event.operation.operation_id
            ):
                raise ValueError(
                    "Known construction fact requires its exact append operation"
                )
        elif not isinstance(work, ObserveConstructionWork) and op.mode != "execute":
            raise ValueError("Cleanup cannot schedule new construction work")
        if isinstance(work, GenerateConstructionWork):
            call, request = work.planned.call, work.request
            if (
                work.planned.operation != op
                or call.role != "generator"
                or (
                    call.request_id,
                    call.candidate_slot,
                    call.resample_index,
                    call.seed,
                    call.temperature,
                )
                != (
                    request.request_id,
                    request.candidate_index,
                    request.resample_index,
                    request.seed,
                    request.temperature,
                )
            ):
                raise ValueError(
                    "Original registered Generator input/sampling required"
                )
            run_level(work.invoke_operation)
            if work.invoke_operation.mode != "execute":
                raise ValueError(
                    "Generator invocation requires original execute operation"
                )
        if (
            isinstance(work, ReviseConstructionWork)
            and work.original.preparation.operation != op
        ):
            raise ValueError(
                "Teacher step must retain original assembly/send operation"
            )
        if isinstance(work, ExecuteConstructionWork):
            binding, invoke = work.planned.intent.binding, work.invoke_operation
            if (
                work.planned.operation != op
                or binding.run != self.run
                or (invoke.run_id, invoke.owner_id, invoke.attempt_id, invoke.mode)
                != (owner.run_id, owner.owner_id, binding.attempt_id, "execute")
            ):
                raise ValueError(
                    "Actor lifecycle must retain original intent/attempt execute scope"
                )
        if isinstance(
            work,
            (GenerateConstructionWork, ReviseConstructionWork, ExecuteConstructionWork),
        ):
            complete = work.completion_operation
            run_level(complete)
            operations = [op.operation_id, complete.operation_id]
            if isinstance(work, (GenerateConstructionWork, ExecuteConstructionWork)):
                operations.append(work.invoke_operation.operation_id)
            if len(operations) != len(set(operations)):
                raise ValueError(
                    "Original planning/invocation/completion operations must differ"
                )
            if complete.mode == "cleanup":
                parent = (
                    work.invoke_operation.operation_id
                    if isinstance(work, GenerateConstructionWork)
                    else op.operation_id
                )
                if complete.parent_operation_id != parent:
                    raise ValueError(
                        "Completion cleanup requires original run-level parent"
                    )
        if len(self.model_dump_json().encode()) > 4 * 1024**2:
            raise ValueError(
                "Construction step metadata exceeds complete command bound"
            )
        return self


class ConstructionResult(Contract):
    schema_version: Literal["construction-control-result/1"] = (
        "construction-control-result/1"
    )
    status: Literal["advanced", "waiting", "complete", "observed"]
    progress: ConstructionProgress
    teacher: PublishedTeacherRevisionAssembly | None = None

    @model_validator(mode="after")
    def original_state_status(self) -> Self:
        action = self.progress.project().next_action.kind
        if (self.status == "complete") != (action == "complete"):
            raise ValueError(
                "Complete status must reflect original committed selection"
            )
        if self.status == "waiting" and action not in (
            "await_response",
            "await_attempt",
            "blocked",
        ):
            raise ValueError("Waiting status requires original pending/unknown work")
        if self.teacher is not None and not any(
            isinstance(e, CallPlanned) and e.call == self.teacher.bound.plan.call
            for e in self.progress.events
        ):
            raise ValueError("Teacher result must retain the original registered call")
        return self
