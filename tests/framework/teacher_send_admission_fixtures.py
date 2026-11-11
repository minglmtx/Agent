"""Original construction/run/claim/paid ledger with explicit synthetic rights."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
)
from lab_generate_skill.application.teacher_assembly import assemble_teacher_revision
from lab_generate_skill.application.teacher_revision import RecordedTeacher
from lab_generate_skill.application.teacher_send_admission import (
    ConstructionTeacherSendAuthority,
    TeacherSendAdmissionDeps,
)
from lab_generate_skill.bootstrap.teacher_assembly import assembled_teacher
from lab_generate_skill.domain.teacher_assembly import PublishedTeacherRevisionAssembly
from lab_generate_skill.domain.model_request import ResolvedModelRequest
from lab_generate_skill.domain.errors import EvidenceNotFound
from teacher_assembly_fixtures import assembly_case, AssemblyCase
from teacher_source_admission_fixtures import admit_native_source, SourceAdmissionCase


@dataclass
class TeacherSendCase:
    native: AssemblyCase
    source: SourceAdmissionCase
    published: PublishedTeacherRevisionAssembly
    gate: ConstructionTeacherSendAuthority
    resolved: ResolvedModelRequest

    def teacher(self) -> RecordedTeacher:
        c = self.native
        return assembled_teacher(
            self.published,
            c.review,
            c.original.preparation.policy,
            ledger=c.ledger,
            transport=c.transport,
            evidence=c.source.data.store,
            controls=c.source.controls,
            source_authority=c.send_authority,
            context_authority=c.context,
            counts=c.count_review,
            runs=self.source.runs,
            claims=self.source.deps.claims,
        )


def send_case(root: Path) -> TeacherSendCase:
    c = assembly_case(root)
    source = admit_native_source(c.source, construction=c.deps.journal)
    published = assemble_teacher_revision(
        c.original, c.deps, control=c.source.controls.bind(c.source.operation)
    )
    plan = published.bound.plan
    c.send_authority.expected = plan
    plans = EvidenceTeacherRevisionPlans(
        {plan.revision.request_id: published.bound.reference}, c.source.data.store
    )
    gate = ConstructionTeacherSendAuthority(
        c.source.data.plan.run,
        plans,
        TeacherSendAdmissionDeps(
            c.deps.journal,
            source.runs,
            source.deps.claims,
            c.deps.plans,
            c.ledger,
            c.send_authority,
        ),
        c.source.controls,
    )
    resolved = ResolvedModelRequest(
        request=plan.send.reservation.request,
        input_bytes=c.source.data.store.read(plan.send.input_ref),
        parameters_bytes=c.source.data.store.read(plan.send.parameters_ref),
        limits=plan.send.limits,
    )
    # Read-only installation preparation of the ledger's stable lock, not a reservation.
    try:
        c.ledger.read(plan.send.reservation.request, plan.send.operation)
    except EvidenceNotFound:
        pass
    else:
        raise AssertionError("Fresh unit source already has a paid request")
    return TeacherSendCase(c, source, published, gate, resolved)
