"""Original file construction history plus explicitly approved synthetic parts.

Source authority registers exact fixture views/trace-marker refs; it does not
qualify actual Actor trace leaves, feedback filtering, source execution or fees.
"""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.domain.teacher_source import (
    TeacherSourceBindings,
    TeacherAttemptSource,
    TeacherAttemptView,
)
from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.teacher_input import native_evidence
from lab_generate_skill.domain.teacher_json import array_value, object_value, json_value
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.bootstrap.teacher_source import teacher_source_dependencies
from lab_generate_skill.application.teacher_source import TeacherSourceDeps
from construction_storage_fixtures import fixture, StorageFixture
from teacher_context_fixtures import teacher_projection_case
from test_run_journal import command, CancelSwitch


class UnitTeacherSourceAuthority:
    def __init__(
        self, progress: ConstructionProgress, bindings: TeacherSourceBindings
    ) -> None:
        self.progress, self.bindings = progress, bindings
        self.denied = False
        self.pending = False
        self.prepares = 0
        self.reviews = 0

    def _same(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        if self.denied or progress != self.progress or bindings != self.bindings:
            raise OwnershipConflict(
                "Original unit approved source/trace/feedback provenance differs"
            )

    def verify_prepare(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        *,
        control: OperationControl,
    ) -> None:
        self.prepares += 1
        self._same(progress, bindings, control)
        if self.pending:
            raise OwnershipConflict(
                "Original unit source has an unknown request; no new ID or format"
            )

    def verify_recorded(
        self,
        progress: ConstructionProgress,
        bindings: TeacherSourceBindings,
        *,
        control: OperationControl,
    ) -> None:
        self.reviews += 1
        self._same(progress, bindings, control)


@dataclass
class TeacherSourceCase:
    data: StorageFixture
    progress: ConstructionProgress
    bindings: TeacherSourceBindings
    controls: OperationGuards
    authority: UnitTeacherSourceAuthority
    observations: EvidenceObservations
    retrieval: EvidenceRetrievalRecords
    deps: TeacherSourceDeps


def source_case(
    root: Path,
    site: Site = "map",
    *,
    round_number: int = 1,
    first_success: bool = False,
) -> TeacherSourceCase:
    root.mkdir()
    data = fixture(root, site=site)
    journal = data.journal()
    progress = journal.create(data.plan, command())
    while True:
        action = progress.project().next_action
        if action.kind == "revise" and action.candidate_slot == round_number + 3:
            break
        status = "failure"
        if (
            first_success
            and action.kind == "await_attempt"
            and len(progress.project().attempts) == 0
        ):
            status = "success"
        event = data.event(progress, status=status)
        progress = journal.append(event, progress.revision, event.operation)
    controls = OperationGuards(SystemClock(), CancelSwitch())
    operation = command("original-teacher-source-send")
    control = controls.bind(operation)

    def put(
        raw: bytes,
        schema: str,
        visibility: str = "teacher",
        media: str = "application/json",
    ) -> EvidenceRef:
        return data.store.put(
            raw,
            EvidenceMetadata.model_validate(
                dict(
                    media_type=media,
                    content_schema=schema,
                    visibility=visibility,
                    producer="unit-approved-teacher-source",
                )
            ),
            control,
        )

    instructions = put(
        b"Exact original Teacher instructions and skills\n",
        "teacher-instructions/1",
        media="text/plain",
    )
    public = PublicConstructionContext.model_validate_json(
        data.store.read(data.plan.public_context_ref)
    )
    scope = TeacherContextScope(
        owner=data.plan.run.owner,
        task=public.task.identity,
        context_id=public.context_id,
    )
    seed_source = teacher_projection_case(site)
    original = array_value(
        native_evidence(seed_source.allowed.messages[1].content)["attempts"],
        "original fixture attempts",
    )
    view = progress.project()
    sources = []
    for index, result in enumerate(view.attempts):
        native = deepcopy(
            object_value(original[index % len(original)], "complete fixture attempt")
        )
        native.update(
            skill=json_value(
                view.candidates[
                    result.intent.candidate_slot
                ].response.skill.model_payload()
            ),
            steps=result.interactions,
            reward=result.evaluation.reward,
            success=result.evaluation.status == "success",
            generation_rounds=result.generations,
        )
        native["extra_original_fields"] = {
            "candidate_slot": result.intent.candidate_slot,
            "round": max(0, result.intent.candidate_slot - 3),
            "opaque": [1, 1.0, True, "全部早期步骤"],
        }
        native["evaluator_feedback"] = {
            "available": True,
            "status": result.evaluation.status,
            "reward": result.evaluation.reward,
            "private_reference_withheld": True,
            "checks": [
                {"name": "unit_goal", "passed": result.evaluation.status == "success"}
            ],
        }
        allowed = TeacherAttemptView(
            scope=scope,
            attempt_id=result.intent.binding.attempt_id,
            candidate_slot=result.intent.candidate_slot,
            native=native,
        )
        allowed_ref = put(allowed.model_dump_json().encode(), "teacher-attempt-input/1")
        marker = (
            "explicit synthetic only:" + result.intent.binding.attempt_id
        ).encode()
        actor = put(marker, "actor-run-request/2", "private")
        trace = put(marker + b":trace", "interaction-trace/1", "private")
        sources.append(
            TeacherAttemptSource(
                attempt_id=result.intent.binding.attempt_id,
                candidate_slot=result.intent.candidate_slot,
                allowed_view_ref=allowed_ref,
                actor_request_ref=actor,
                trace_ref=trace,
            )
        )
    bindings = TeacherSourceBindings(
        request_id="original-teacher-round-" + str(round_number),
        operation=operation,
        teacher_round=round_number,
        instructions_ref=instructions,
        attempts=tuple(sources),
    )
    authority = UnitTeacherSourceAuthority(progress, bindings)
    observations = EvidenceObservations(data.store, controls)
    retrieval = EvidenceRetrievalRecords(data.store, controls, data.retrieval_authority)
    deps = teacher_source_dependencies(data.store, observations, retrieval, authority)
    return TeacherSourceCase(
        data, progress, bindings, controls, authority, observations, retrieval, deps
    )
