"""Original file history/native source fixture; no production permission defaults."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.application.teacher_source import (
    TeacherSourceDeps,
    publish_teacher_source,
)
from lab_generate_skill.application.teacher_source_review import TeacherSourceReviewDeps
from lab_generate_skill.application.teacher_attempt import publish_teacher_attempt
from lab_generate_skill.application.teacher_attempt_authority import (
    NativeTeacherSourceAuthority,
)
from lab_generate_skill.application.teacher_attempt_review import (
    TeacherAttemptReviewDeps,
)
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.traces import EvidenceTraceRecords
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.bootstrap.teacher_attempt import (
    native_teacher_attempt_review,
    native_teacher_source_authority,
)
from lab_generate_skill.bootstrap.teacher_source import teacher_source_dependencies
from lab_generate_skill.domain.construction import AttemptCompleted
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.teacher_attempt import PublishedTeacherAttempt
from lab_generate_skill.domain.teacher_source import (
    TeacherSourceBindings,
    PublishedTeacherSource,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from teacher_attempt_fixtures import (
    native_attempt_case,
    UnitTraceAuthority,
    UnitNativeAuthority,
)
from teacher_source_fixtures import UnitTeacherSourceAuthority
from construction_storage_fixtures import fixture, StorageFixture
from test_run_journal import command, CancelSwitch


@dataclass
class NativeSourceCase:
    data: StorageFixture
    progress: ConstructionProgress
    operation: OperationContext
    parts: tuple[PublishedTeacherAttempt, ...]
    bindings: TeacherSourceBindings
    source: PublishedTeacherSource
    authority: UnitTeacherSourceAuthority
    source_authority: NativeTeacherSourceAuthority
    native_review: TeacherAttemptReviewDeps
    observations: EvidenceObservations
    retrieval: EvidenceRetrievalRecords
    controls: OperationGuards

    def review_source(self, operation: OperationContext) -> TeacherSourceReviewDeps:
        authority = native_teacher_source_authority(
            self.authority, self.parts, self.native_review, operation
        )
        return TeacherSourceReviewDeps(
            self.data.store, self.observations, self.retrieval, authority, operation
        )


def native_source_case(
    root: Path,
    site: Site = "map",
    *,
    recorded_teacher: bool = False,
    round_number: int = 1,
) -> NativeSourceCase:
    root.mkdir()
    data = fixture(
        root,
        site=site,
        recorded_teacher=recorded_teacher,
        allowed_actions=("click", "send_msg_to_user"),
    )
    journal = data.journal()
    progress = journal.create(data.plan, command())
    controls = OperationGuards(SystemClock(), CancelSwitch())
    operation = command("original-native-teacher-round" + str(round_number))
    public = PublicConstructionContext.model_validate_json(
        data.store.read(data.plan.public_context_ref)
    )
    parts = []
    while not (
        progress.project().next_action.kind == "revise"
        and progress.project().next_action.candidate_slot == round_number + 3
    ):
        event = data.event(progress)
        if isinstance(event, AttemptCompleted):
            old = event.result
            scope = StateScope(
                owner=progress.plan.run.owner,
                task=progress.plan.task.identity,
                context_id=public.context_id,
                attempt_id=old.intent.binding.attempt_id,
            )
            c = native_attempt_case(
                root / ("attempt-" + str(old.intent.candidate_slot)),
                site,
                original_scope=scope,
                task=public.task,
                skill=progress.project()
                .candidates[old.intent.candidate_slot]
                .response.skill,
                candidate_slot=old.intent.candidate_slot,
                source_operation=operation,
                shared_store=data.store,
            )
            published = publish_teacher_attempt(
                c.original, c.deps, control=controls.bind(operation)
            )
            parts.append(published)
            # The original journal records the new original native result once,
            # before composing Teacher input; no detached history rewrite.
            from construction_storage_fixtures import put as fixture_put

            actual_attempt_ref = fixture_put(
                data.store,
                {
                    "intent": old.intent.model_dump(mode="json"),
                    "interactions": c.trace.interactions,
                    "generations": c.trace.generations,
                    "unit_closed": True,
                },
                "attempt-result/1",
            )
            event = event.model_copy(
                update={
                    "result": old.model_copy(
                        update={
                            "attempt_ref": actual_attempt_ref,
                            "evaluation": c.evaluation,
                            "evaluation_ref": c.original.evaluation_ref,
                            "interactions": c.trace.interactions,
                            "generations": c.trace.generations,
                        }
                    )
                }
            )
        progress = journal.append(event, progress.revision, event.operation)
    assert progress == journal.read(command()) and len(parts) == round_number + 3
    instructions = data.store.put(
        b"Original Teacher instructions/skill contract.\n",
        EvidenceMetadata(
            media_type="text/plain",
            content_schema="teacher-instructions/1",
            visibility="teacher",
            producer="unit-native-source",
        ),
    )
    bindings = TeacherSourceBindings(
        request_id="original-native-revision" + str(round_number),
        operation=operation,
        teacher_round=round_number,
        instructions_ref=instructions,
        attempts=tuple(p.source for p in parts),
    )
    original = UnitTeacherSourceAuthority(progress, bindings)
    observations = EvidenceObservations(data.store, controls)
    traces = EvidenceTraceRecords(data.store, controls, UnitTraceAuthority())
    native_review = native_teacher_attempt_review(
        data.store, observations, traces, UnitNativeAuthority()
    )
    source_authority = native_teacher_source_authority(
        original, tuple(parts), native_review, operation
    )
    retrieval = EvidenceRetrievalRecords(data.store, controls, data.retrieval_authority)
    source = publish_teacher_source(
        progress,
        bindings,
        teacher_source_dependencies(
            data.store, observations, retrieval, source_authority
        ),
        control=controls.bind(operation),
    )
    return NativeSourceCase(
        data,
        progress,
        operation,
        tuple(parts),
        bindings,
        source,
        original,
        source_authority,
        native_review,
        observations,
        retrieval,
        controls,
    )
