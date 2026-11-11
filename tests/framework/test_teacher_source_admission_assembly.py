"""Original source ownership reaches original prepared Teacher/once/journal.

All physical ACL/provider/count/fee permissions synthetic; no actual API/site.
"""

from dataclasses import replace
from pathlib import Path
from datetime import datetime, timezone
import pytest
from lab_generate_skill.application.teacher_assembly import assemble_teacher_revision
from lab_generate_skill.application.teacher_source_review import (
    TeacherSourceReviewDeps,
    review_teacher_source,
)
from lab_generate_skill.application.teacher_source_authority import (
    RecordedTeacherSourceAuthority,
)
from lab_generate_skill.bootstrap.teacher_source import teacher_source_authority
from lab_generate_skill.bootstrap.teacher_assembly import assembled_teacher
from lab_generate_skill.bootstrap.teacher_revision import recorded_teacher_review
from lab_generate_skill.bootstrap.teacher_transaction_review import (
    transaction_teacher_review,
)
from lab_generate_skill.bootstrap.teacher_source_admission import (
    qualified_native_teacher_source,
)
from lab_generate_skill.ports.construction import ConstructionJournal
from lab_generate_skill.ports.teacher_revision import TeacherConstructionVerifier
from lab_generate_skill.adapters.plans.teacher_revision import (
    EvidenceTeacherRevisionPlans,
)
from lab_generate_skill.domain.construction import CallCompleted
from lab_generate_skill.domain.errors import OwnershipConflict
from teacher_assembly_fixtures import assembly_case
from teacher_source_admission_fixtures import admit_native_source
from test_teacher_assembly import paid_files
from test_run_journal import command


@pytest.mark.parametrize("revoke", [False, True])
def test_original_claim_native_source_to_teacher_once_and_journal_or_revocation_before_send(
    tmp_path: Path, revoke: bool
) -> None:
    c = assembly_case(tmp_path / "case")
    n = c.source
    a = admit_native_source(n, construction=c.deps.journal)
    source = TeacherSourceReviewDeps(
        n.data.store, n.observations, n.retrieval, a.authority, n.operation
    )
    assert isinstance(c.context, RecordedTeacherSourceAuthority)
    context = teacher_source_authority(
        c.context.original,
        n.source,
        evidence=n.data.store,
        observations=n.observations,
        retrieval=n.retrieval,
        authority=a.authority,
        operation=n.operation,
    )
    # Counts and original complete source bytes are unchanged; independent review rebinds them.
    deps = replace(
        c.deps, source=source, context=replace(c.deps.context, authority=context)
    )
    review = replace(
        c.review, source=source, context=replace(c.review.context, authority=context)
    )
    n.authority.denied = True
    published = assemble_teacher_revision(
        c.original, deps, control=n.controls.bind(n.operation)
    )
    c.send_authority.expected = published.bound.plan
    teacher = assembled_teacher(
        published,
        review,
        published.bound.plan.preparation.policy,
        ledger=c.ledger,
        transport=c.transport,
        evidence=n.data.store,
        controls=n.controls,
        source_authority=c.send_authority,
        context_authority=context,
        counts=c.count_review,
        runs=a.runs,
        claims=a.deps.claims,
    )
    before = paid_files(c)
    if revoke:
        n.data.claim_authority.denied = True
        with pytest.raises(OwnershipConflict, match="claim caller denied"):
            teacher.revise(published.bound.plan.revision, n.operation)
        assert paid_files(c) == before and not c.transport.calls
        assert (
            deps.journal.read(n.operation).project().pending_call
            == published.bound.plan.call
        )
        return
    result = teacher.revise(published.bound.plan.revision, n.operation)
    assert len(c.transport.calls) == 1 and c.counts.calls == 2
    read_op = n.operation.cleanup(
        "source-admitted-transaction-read", now=datetime.now(timezone.utc), seconds=60
    )

    def bind_snapshot(snapshot: ConstructionJournal) -> TeacherConstructionVerifier:
        snapshot_source = qualified_native_teacher_source(
            n.data.plan.run,
            replace(a.deps, construction=snapshot),
            n.parts,
            n.native_review,
            read_op,
        )
        snapshot_context = teacher_source_authority(
            context.original,
            n.source,
            evidence=n.data.store,
            observations=n.observations,
            retrieval=n.retrieval,
            authority=snapshot_source,
            operation=read_op,
        )
        return recorded_teacher_review(
            EvidenceTeacherRevisionPlans(
                {result.request_id: published.bound.reference}, n.data.store
            ),
            published.bound.plan.preparation.policy,
            evidence=n.data.store,
            controls=n.controls,
            context_authority=snapshot_context,
            counts=c.count_review,
        )

    proof = transaction_teacher_review(bind_snapshot, read_op, controls=n.controls)
    journal = n.data.journal(teacher_review=proof)
    old = journal.read(n.operation)
    event = CallCompleted(
        operation=command("source-admitted-teacher-complete"), response=result
    )
    final = journal.append(event, old.revision, event.operation)
    assert (
        final.project().pending_call is None
        and final.project().next_action.candidate_slot == 4
    )
    assert final.project().next_action.kind == "execute"
    assert (
        len(c.transport.calls) == 1
        and a.runs.read(n.operation).project()[0].stage == "running"
    )
    after = n.operation.cleanup(
        "source-after-real-journal-commit", now=datetime.now(timezone.utc), seconds=60
    )
    actual = review_teacher_source(
        n.source,
        TeacherSourceReviewDeps(
            n.data.store, n.observations, n.retrieval, a.recorded(after), after
        ),
        control=n.controls.bind(after),
    )
    assert actual.source == n.source.source and len(c.transport.calls) == 1
