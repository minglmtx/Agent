"""Read complete approved parts and bind them to the original frozen schedule.

Source-specific filtering lives before teacher-visible refs; no raw private DB,
expected answer or dependency container is parsed into model messages here.
"""

from dataclasses import dataclass
from pydantic import TypeAdapter
from lab_generate_skill.domain.construction_state import (
    ConstructionProgress,
    select_target,
)
from lab_generate_skill.domain.construction import CallPlanned
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.teacher_source import (
    TeacherSourceBindings,
    TeacherAttemptView,
)
from lab_generate_skill.domain.task_teacher import TaskTeacherReceipt
from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.domain.retrieval import RetrievalQuery
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.teacher_json import same_json, MAX_TEACHER_BYTES
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.retrieval import RetrievalRecords
from .context_evidence import read_bytes
from .teacher_actor_reads import canonical

_SKILLS = TypeAdapter(tuple[CompactSkill, ...])


@dataclass(frozen=True)
class TeacherSourceParts:
    scope: TeacherContextScope
    public: PublicConstructionContext
    initial: str
    skills: tuple[CompactSkill, ...]
    attempts: tuple[TeacherAttemptView, ...]
    best: int | None


def check_source_schedule(
    progress: ConstructionProgress, bindings: TeacherSourceBindings
) -> None:
    view = progress.project()
    action = view.next_action
    owner = progress.plan.run.owner
    if (bindings.operation.run_id, bindings.operation.owner_id) != (
        owner.run_id,
        owner.owner_id,
    ):
        raise OwnershipConflict("Teacher source changed original construction owner")
    if action.kind != "revise" or action.candidate_slot != bindings.teacher_round + 3:
        raise OwnershipConflict(
            "Teacher source requires original ready revision; unknown/pending cannot replay"
        )
    if tuple(
        (a.intent.binding.attempt_id, a.intent.candidate_slot) for a in view.attempts
    ) != tuple((a.attempt_id, a.candidate_slot) for a in bindings.attempts):
        raise OwnershipConflict(
            "Teacher source must contain every original attempt in order"
        )
    if any(
        isinstance(e, CallPlanned) and e.call.request_id == bindings.request_id
        for e in progress.events
    ):
        raise OwnershipConflict(
            "Registered Teacher request cannot be renewed by a source format"
        )


def read_parts(
    progress: ConstructionProgress,
    bindings: TeacherSourceBindings,
    evidence: EvidenceReader,
    observations: ObservationLoader,
    retrieval: RetrievalRecords,
    operation: OperationContext,
    *,
    control: OperationControl,
) -> TeacherSourceParts:
    check_source_schedule(progress, bindings)
    ref = progress.plan.public_context_ref
    raw = read_bytes(evidence, ref, 1024**2, control)
    public = PublicConstructionContext.model_validate_json(raw)
    if (
        public.model_dump_json().encode() != raw
        or public.task.identity != progress.plan.task.identity
    ):
        raise EvidenceIntegrityError("Teacher source changed qualified public context")
    initial = observations.load(public.initial_observation_ref, operation)
    initial.record.check_initial(public.task.identity, public.context_id)
    if initial.text is None:
        raise EvidenceIntegrityError(
            "Teacher needs complete original initial text, including legal empty text"
        )
    scope = TeacherContextScope(
        owner=progress.plan.run.owner,
        task=public.task.identity,
        context_id=public.context_id,
    )
    query = RetrievalQuery(
        task=public.task.identity, literal_goal=public.task.goal, public_context_ref=ref
    )
    skills = _SKILLS.validate_python(
        retrieval.load(
            progress.plan.retrieval_ref, query, progress.plan.retrieval_scope, operation
        ),
        strict=True,
    )
    if len(skills) != progress.plan.method.top_k:
        raise EvidenceIntegrityError(
            "Teacher source requires original complete top-k retrieval"
        )
    view = progress.project()
    attempts = []
    for index, (source, result) in enumerate(
        zip(bindings.attempts, view.attempts, strict=True)
    ):
        expected_scope = scope
        if bindings.schema_version == "teacher-source-bindings/2":
            assert bindings.task_receipt_refs is not None
            task = canonical(
                bindings.task_receipt_refs[index],
                "task-teacher-receipt/1",
                TaskTeacherReceipt,
                evidence,
                control,
                512 * 1024,
            )
            if (
                task.part.source != source
                or task.original.result != result
                or (task.original.scope.owner, task.original.scope.task)
                != (scope.owner, scope.task)
            ):
                raise EvidenceIntegrityError(
                    "Task attempt view changed complete original source provenance"
                )
            # Its measured equivalence is independently required by the task
            # authority. Preserve the actual candidate context, never relabel it
            # as the immutable source page's context to satisfy a scope check.
            expected_scope = task.original.scope
        raw = read_bytes(evidence, source.allowed_view_ref, MAX_TEACHER_BYTES, control)
        allowed = TeacherAttemptView.model_validate_json(raw)
        if allowed.model_dump_json().encode() != raw or (
            allowed.scope,
            allowed.attempt_id,
            allowed.candidate_slot,
        ) != (expected_scope, source.attempt_id, source.candidate_slot):
            raise EvidenceIntegrityError(
                "Allowed attempt changed original source/slot/scope"
            )
        native = allowed.native
        skill = view.candidates[result.intent.candidate_slot].response.skill
        status = result.evaluation.status
        success = (
            True if status == "success" else False if status == "failure" else None
        )
        if (
            not same_json(native["skill"], skill.model_payload())
            or type(native["success"]) is not type(success)
            or native["success"] != success
            or type(native["steps"]) is not int
            or native["steps"] != result.interactions
            or type(native["reward"]) is not type(result.evaluation.reward)
            or native["reward"] != result.evaluation.reward
        ):
            raise EvidenceIntegrityError(
                "Allowed attempt changed original skill/status/reward/actual interactions"
            )
        if "generation_rounds" in native and (
            type(native["generation_rounds"]) is not int
            or native["generation_rounds"] != result.generations
        ):
            raise EvidenceIntegrityError(
                "Allowed attempt changed original model generation count"
            )
        attempts.append(allowed)
    selection = select_target(view.attempts)
    best = (
        None
        if selection.attempt_id is None
        else next(
            i
            for i, a in enumerate(view.attempts)
            if a.intent.binding.attempt_id == selection.attempt_id
        )
    )
    control.checkpoint()
    return TeacherSourceParts(
        scope, public, initial.text, skills, tuple(attempts), best
    )
