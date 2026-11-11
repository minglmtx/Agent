"""Publish a native allowed attempt over the original controlled CAS.

No model, counter, browser, ledger registration or replacement runner. The input
and immutable receipt bind all private leaves; only the allowlisted native view
is Teacher-visible. All uncertain writes preserve their original references.
"""

from dataclasses import dataclass
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.teacher_attempt import (
    TeacherAttemptInput,
    TeacherAttemptReceipt,
    PublishedTeacherAttempt,
)
from lab_generate_skill.domain.teacher_source import (
    TeacherAttemptSource,
    TeacherAttemptView,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.observations import ObservationLoader
from lab_generate_skill.ports.traces import TraceRecords
from lab_generate_skill.ports.teacher_attempt import (
    TeacherAttemptAuthority,
    TeacherAttemptComposer,
    TeacherAttemptVerifier,
)
from .teacher_actor_reads import read_actor_material
from .context_evidence import publish_raw


@dataclass(frozen=True)
class TeacherAttemptDeps:
    evidence: EvidenceStore
    observations: ObservationLoader
    traces: TraceRecords
    authority: TeacherAttemptAuthority
    compose: TeacherAttemptComposer
    verify: TeacherAttemptVerifier


class TeacherAttemptUnconfirmed(RuntimeError):
    def __init__(
        self,
        original: TeacherAttemptInput,
        phase: str,
        primary: BaseException,
        retained: tuple[EvidenceRef, ...],
    ) -> None:
        self.original, self.phase, self.primary, self.retained = (
            original,
            phase,
            primary,
            retained,
        )
        super().__init__(
            "Original Teacher attempt projection unresolved; preserve facts, never rerun Actor"
        )


def publish_teacher_attempt(
    original: TeacherAttemptInput,
    deps: TeacherAttemptDeps,
    *,
    control: OperationControl,
) -> PublishedTeacherAttempt:
    original = TeacherAttemptInput.model_validate(original)
    retained: list[EvidenceRef] = []
    phase = "read_originals"
    try:
        control.checkpoint()
        material = read_actor_material(
            original,
            deps.evidence,
            deps.observations,
            deps.traces,
            original.operation,
            control=control,
        )
        phase = "source_permission"
        deps.authority.verify_allowed(
            original,
            material.request,
            material.trace,
            material.evaluation,
            control=control,
        )
        control.checkpoint()
        phase = "complete_projection"
        allowed = TeacherAttemptView.model_validate(deps.compose(material))
        deps.verify(material, allowed)
        raw = allowed.model_dump_json().encode()
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema="teacher-attempt-input/1",
            visibility="teacher",
            producer="teacher-original-actor-attempt",
        )
        source = TeacherAttemptSource(
            attempt_id=material.request.scope.attempt_id,
            candidate_slot=original.candidate_slot,
            allowed_view_ref=evidence_reference(raw, metadata),
            actor_request_ref=original.actor_request_ref,
            trace_ref=original.trace_ref,
        )
        receipt = TeacherAttemptReceipt(original=original, source=source)
        receipt_raw = receipt.model_dump_json().encode()
        phase = "publish_allowed"
        returned = publish_raw(deps.evidence, raw, metadata, retained, control)
        if returned != source.allowed_view_ref:
            raise EvidenceIntegrityError(
                "Native allowed attempt publication changed reference"
            )
        phase = "publish_provenance"
        receipt_ref = publish_raw(
            deps.evidence,
            receipt_raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="teacher-attempt-source-receipt/1",
                visibility="private",
                producer="teacher-original-actor-attempt",
            ),
            retained,
            control,
        )
        return PublishedTeacherAttempt(receipt_ref=receipt_ref, source=source)
    except BaseException as error:
        raise TeacherAttemptUnconfirmed(
            original, phase, error, tuple(retained)
        ) from error
