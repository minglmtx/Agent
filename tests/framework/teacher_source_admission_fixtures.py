"""Real original claims/context/construction/run files, synthetic physical ACLs.

Reuses already prepared native parts; no Actor/Teacher/browser/model replay.
Run closure events are explicit fixture facts, never a real resource proof.
"""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.application.teacher_source_admission import (
    TeacherConstructionSourceDeps,
)
from lab_generate_skill.application.teacher_attempt_authority import (
    NativeTeacherSourceAuthority,
)
from lab_generate_skill.bootstrap.teacher_source_admission import (
    qualified_native_teacher_source,
)
from lab_generate_skill.domain.execution import AttemptStage
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_journal import AttemptEntry
from lab_generate_skill.ports.construction import ConstructionJournal
from teacher_native_source_fixtures import NativeSourceCase
from test_run_journal import Harness


@dataclass
class SourceAdmissionCase:
    native: NativeSourceCase
    deps: TeacherConstructionSourceDeps
    runs: FileRunJournal
    harness: Harness
    authority: NativeTeacherSourceAuthority

    def recorded(self, operation: OperationContext) -> NativeTeacherSourceAuthority:
        return qualified_native_teacher_source(
            self.native.data.plan.run,
            self.deps,
            self.native.parts,
            self.native.native_review,
            operation,
        )


def admit_native_source(
    native: NativeSourceCase,
    *,
    construction: ConstructionJournal | None = None,
    omit_last: bool = False,
    unsealed_last: bool = False,
) -> SourceAdmissionCase:
    d = native.data
    root = d.root / "source-run-journal"
    root.mkdir()
    plans = EvidenceRunPlans(d.store, native.controls)
    run = plans.load(d.plan.run, native.operation)
    runs = FileRunJournal(
        root, d.plan.run, native.controls, d.store, capacity=run.run_capacity
    )
    from test_run_journal import CancelSwitch

    harness = Harness(
        root,
        d.store,
        runs,
        d.plan.run,
        d.plan.claim_ref,
        CancelSwitch(),
        run.run_capacity,
    )
    snapshot = harness.running()
    results = native.progress.project().attempts
    stages: tuple[AttemptStage, ...] = (
        "planned",
        "acquiring",
        "preparing",
        "starting",
        "baseline_verified",
        "executing",
        "captured",
        "evaluated",
        "closing",
        "restoring",
        "sealed",
    )
    for index, result in enumerate(results):
        if omit_last and index == len(results) - 1:
            continue
        chosen = stages[:-3] if unsealed_last and index == len(results) - 1 else stages
        for stage in chosen:
            proposed = harness.attempt_entry(
                snapshot, result.intent.binding.attempt_id, stage
            )
            entry = AttemptEntry(binding=result.intent.binding, event=proposed.event)
            snapshot = runs.append(entry, snapshot.revision, entry.event.operation)
    deps = TeacherConstructionSourceDeps(
        construction or d.journal(),
        runs,
        d.claims(),
        EvidenceContextRecords(d.store, native.controls, d.context_authority),
        plans,
        d.authority,
    )
    authority = qualified_native_teacher_source(
        d.plan.run, deps, native.parts, native.native_review, native.operation
    )
    return SourceAdmissionCase(native, deps, runs, harness, authority)
