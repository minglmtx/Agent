"""Publish approved complete construction evidence over original CAS and ports.

No model/counter/ledger intent or website effect. This is source assembly, not
qualification of raw traces: mandatory original authority checks those leaves.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.teacher_source import (
    TeacherSourceBindings,
    TeacherSourceReceipt,
    PublishedTeacherSource,
)
from lab_generate_skill.domain.context_projection import TeacherContextSource
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.teacher_input import AllowedTeacherEvidence
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.retrieval import RetrievalRecords
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.teacher_source import (
    TeacherSourceAuthority,
    TeacherSourceComposer,
)
from .teacher_source_inputs import read_parts, check_source_schedule
from .context_evidence import publish_raw, read_bytes


@dataclass(frozen=True)
class TeacherSourceDeps:
    evidence: EvidenceStore
    observations: ObservationLoader
    retrieval: RetrievalRecords
    authority: TeacherSourceAuthority
    compose: TeacherSourceComposer


class TeacherSourceUnconfirmed(RuntimeError):
    def __init__(
        self,
        bindings: TeacherSourceBindings,
        phase: str,
        primary: BaseException,
        retained: tuple[EvidenceRef, ...],
    ) -> None:
        self.bindings, self.phase, self.primary, self.retained = (
            bindings,
            phase,
            primary,
            retained,
        )
        super().__init__(
            "Original Teacher source unresolved; preserve complete facts and do not dispatch"
        )


def publish_teacher_source(
    progress: ConstructionProgress,
    bindings: TeacherSourceBindings,
    deps: TeacherSourceDeps,
    *,
    control: OperationControl,
) -> PublishedTeacherSource:
    progress = ConstructionProgress.model_validate(progress)
    bindings = TeacherSourceBindings.model_validate(bindings)
    retained: list[EvidenceRef] = []
    phase = "authority"
    try:
        control.checkpoint()
        check_source_schedule(progress, bindings)
        deps.authority.verify_prepare(progress, bindings, control=control)
        phase = "complete_allowed_parts"
        parts = read_parts(
            progress,
            bindings,
            deps.evidence,
            deps.observations,
            deps.retrieval,
            bindings.operation,
            control=control,
        )
        phase = "instructions"
        text = read_bytes(
            deps.evidence, bindings.instructions_ref, 256 * 1024, control
        ).decode("utf-8")
        phase = "compose"
        allowed = AllowedTeacherEvidence.model_validate(
            deps.compose(
                parts.scope,
                parts.public.task,
                bindings.teacher_round,
                text,
                parts.initial,
                parts.skills,
                parts.attempts,
                parts.best,
            )
        )
        if (allowed.scope, allowed.task, allowed.teacher_round) != (
            parts.scope,
            parts.public.task,
            bindings.teacher_round,
        ):
            raise EvidenceIntegrityError(
                "Teacher composer changed original source/round"
            )
        phase = "publication_preflight"
        progress_raw = progress.model_dump_json().encode()
        if not 0 < len(progress_raw) <= 8 * 1024**2:
            raise EvidenceIntegrityError(
                "Complete construction source history exceeds byte boundary"
            )
        allowed_raw = allowed.model_dump_json().encode()
        progress_meta = EvidenceMetadata(
            media_type="application/json",
            content_schema="construction-progress/1",
            visibility="private",
            producer="teacher-construction-source",
        )
        allowed_meta = EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-input/1",
            visibility="teacher",
            producer="teacher-construction-source",
        )
        progress_ref = evidence_reference(progress_raw, progress_meta)
        source_ref = evidence_reference(allowed_raw, allowed_meta)
        source = TeacherContextSource(
            scope=parts.scope,
            teacher_round=bindings.teacher_round,
            allowed_input_ref=source_ref,
        )
        receipt = TeacherSourceReceipt(
            progress_ref=progress_ref, bindings=bindings, source=source
        )
        receipt_raw = receipt.model_dump_json().encode()
        phase = "publish_progress"
        publish_raw(deps.evidence, progress_raw, progress_meta, retained, control)
        phase = "publish_allowed"
        publish_raw(deps.evidence, allowed_raw, allowed_meta, retained, control)
        phase = "publish_provenance"
        receipt_ref = publish_raw(
            deps.evidence,
            receipt_raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="teacher-source-receipt/1",
                visibility="private",
                producer="teacher-construction-source",
            ),
            retained,
            control,
        )
        return PublishedTeacherSource(receipt_ref=receipt_ref, source=source)
    except BaseException as error:
        raise TeacherSourceUnconfirmed(
            bindings, phase, error, tuple(retained)
        ) from error
