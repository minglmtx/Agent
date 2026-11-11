"""Use existing native Teacher producer/verifier with mandatory original rights."""

from lab_generate_skill.application.task_teacher import TaskTeacherDeps
from lab_generate_skill.application.task_teacher_inputs import TaskTeacherReadDeps
from lab_generate_skill.application.task_teacher_review import TaskTeacherReviewDeps
from lab_generate_skill.ports.evidence import EvidenceStore, EvidenceReader
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.traces import TraceRecords
from lab_generate_skill.ports.run_journal import RunJournal
from lab_generate_skill.ports.state_records import StateRecords
from lab_generate_skill.ports.construction_task_execution import TaskExecutionAuthority
from lab_generate_skill.ports.teacher_attempt import TeacherAttemptAuthority
from .teacher_attempt import native_teacher_attempt, native_teacher_attempt_review


def completed_task_teacher(
    evidence: EvidenceStore,
    runs: RunJournal,
    states: StateRecords,
    closure: TaskExecutionAuthority,
    observations: ObservationLoader,
    traces: TraceRecords,
    source: TeacherAttemptAuthority,
) -> TaskTeacherDeps:
    return TaskTeacherDeps(
        TaskTeacherReadDeps(evidence, runs, states, closure),
        native_teacher_attempt(evidence, observations, traces, source),
    )


def completed_task_teacher_review(
    evidence: EvidenceReader,
    runs: RunJournal,
    states: StateRecords,
    closure: TaskExecutionAuthority,
    observations: ObservationLoader,
    traces: TraceRecords,
    source: TeacherAttemptAuthority,
) -> TaskTeacherReviewDeps:
    return TaskTeacherReviewDeps(
        TaskTeacherReadDeps(evidence, runs, states, closure),
        native_teacher_attempt_review(evidence, observations, traces, source),
    )
