"""Bind complete task sources to the original construction Teacher callbacks.

The existing assembly, Teacher, once ledger and transaction proof own all work.
This root supplies no permission, configuration, queue, retry or model fallback.
"""

from collections.abc import Callable
from dataclasses import replace
from lab_generate_skill.application.construct_targets import (
    ConstructionDeps,
    ConstructionReadiness,
)
from lab_generate_skill.application.context_review import ContextReviewDeps
from lab_generate_skill.application.teacher_source_review import TeacherSourceReviewDeps
from lab_generate_skill.application.teacher_assembly import TeacherAssemblyDeps
from lab_generate_skill.application.teacher_assembly_review import (
    TeacherAssemblyReviewDeps,
)
from lab_generate_skill.application.teacher_source_authority import (
    RecordedTeacherSourceAuthority,
)
from lab_generate_skill.application.teacher_source_admission import (
    ConstructionTeacherSourceAuthority,
)
from lab_generate_skill.application.task_teacher_source import (
    CompletedTaskTeacherSourceAuthority,
)
from lab_generate_skill.domain.teacher_assembly import PublishedTeacherRevisionAssembly
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.model_request import check_model_cleanup
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.context_projection import ContextCountEvidenceVerifier
from lab_generate_skill.ports.model import ModelTransport, ModelSendAuthority
from lab_generate_skill.ports.requests import RequestLedger
from lab_generate_skill.ports.teacher import Teacher
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
)
from .teacher_assembly import assembled_teacher
from .teacher_source import teacher_source_authority
from .teacher_source_admission import qualified_task_teacher_source
from .teacher_revision import recorded_teacher_review
from .teacher_transaction_review import transaction_teacher_review


def completed_task_teacher_dependencies(
    construction: ConstructionDeps,
    assembly: TeacherAssemblyDeps,
    review: TeacherAssemblyReviewDeps,
    *,
    ledger: RequestLedger,
    transport: ModelTransport,
    send_authority: ModelSendAuthority,
    counts: ContextCountEvidenceVerifier,
    read_operation: OperationContext,
    journal_with_review: Callable[[TeacherConstructionVerifier], ConstructionJournal],
) -> ConstructionDeps:
    """Use one original journal, source/context proof and explicit native ports.

    The caller's journal constructor must bind the supplied verifier to that
    same original journal. construct_targets checks its immutable history.
    Binding itself performs no I/O, reserve, dispatch or recovery.
    """
    read_operation = OperationContext.model_validate(read_operation)
    if (
        not isinstance(construction, ConstructionDeps)
        or not isinstance(assembly, TeacherAssemblyDeps)
        or not isinstance(review, TeacherAssemblyReviewDeps)
    ):
        raise ValueError(
            "Original typed construction/assembly/review dependencies required"
        )
    if (
        not isinstance(construction.readiness, ConstructionReadiness)
        or not isinstance(assembly.source, TeacherSourceReviewDeps)
        or not isinstance(review.source, TeacherSourceReviewDeps)
        or not isinstance(assembly.context, ContextReviewDeps)
        or not isinstance(review.context, ContextReviewDeps)
        or not callable(getattr(construction.controls, "bind", None))
    ):
        raise ValueError(
            "Original typed readiness/source/context/operation dependencies required"
        )
    required_ports = (
        (ledger, ("reserve", "mark_dispatching", "settle", "read")),
        (transport, ("validate", "send")),
        (send_authority, ("verify",)),
        (counts, ("verify",)),
    )
    if any(
        not all(callable(getattr(port, method, None)) for method in methods)
        for port, methods in required_ports
    ):
        raise ValueError("Original ledger/transport/authority/count ports required")
    source = review.source.authority
    context = review.context.authority
    if (
        construction.readiness is None
        or assembly.journal is not construction.journal
        or review.journal is not construction.journal
        or assembly.evidence is not review.evidence
        or assembly.source != review.source
        or assembly.context != review.context
        or not isinstance(source, CompletedTaskTeacherSourceAuthority)
        or not isinstance(source.original, ConstructionTeacherSourceAuthority)
        or not isinstance(context, RecordedTeacherSourceAuthority)
        or context.deps != review.source
        or any(value is None for value in (ledger, transport, send_authority, counts))
        or not callable(journal_with_review)
    ):
        raise ValueError(
            "Same original complete task source, journal and required role proofs must be bound"
        )
    original = source.original
    controls = construction.controls

    def teacher(published: PublishedTeacherRevisionAssembly) -> Teacher:
        return assembled_teacher(
            published,
            review,
            published.bound.plan.preparation.policy,
            ledger=ledger,
            transport=transport,
            evidence=assembly.evidence,
            controls=controls,
            source_authority=send_authority,
            context_authority=context,
            counts=counts,
            runs=original.deps.runs,
            claims=original.deps.claims,
        )

    def journal(published: PublishedTeacherRevisionAssembly) -> ConstructionJournal:
        published = PublishedTeacherRevisionAssembly.model_validate(published)
        plan = published.bound.plan
        # Only proof reads can use a fresh bounded parent cleanup. The original
        # send/settlement and its known returned fact remain immutable.
        check_model_cleanup(plan.send.operation, read_operation)

        def bind_snapshot(snapshot: ConstructionJournal) -> TeacherConstructionVerifier:
            complete = qualified_task_teacher_source(
                original.run,
                replace(original.deps, construction=snapshot),
                source.deps,
                read_operation,
            )
            recorded = teacher_source_authority(
                context.original,
                context.published,
                evidence=assembly.evidence,
                observations=review.source.observations,
                retrieval=review.source.retrieval,
                authority=complete,
                operation=read_operation,
            )
            return recorded_teacher_review(
                EvidenceTeacherRevisionPlans(
                    {plan.revision.request_id: published.bound.reference},
                    assembly.evidence,
                ),
                plan.preparation.policy,
                evidence=assembly.evidence,
                controls=controls,
                context_authority=recorded,
                counts=counts,
            )

        proof = transaction_teacher_review(
            bind_snapshot, read_operation, controls=controls
        )
        return journal_with_review(proof)

    return replace(
        construction,
        evidence=assembly.evidence,
        teacher_assembly=assembly,
        teacher_factory=teacher,
        teacher_journal=journal,
    )
