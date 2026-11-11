"""Real journals/CAS for admission; all environment/permission facts are synthetic."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, cast
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.plans.candidate_inputs import EvidenceCandidateInputs
from lab_generate_skill.adapters.plans.context_evidence import ContextEvidenceReader
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.application.admit_candidate import CandidateAdmissionDeps
from lab_generate_skill.domain.actor_admission import (
    ActorAdmissionRequest,
    CandidateFacts,
)
from lab_generate_skill.domain.baseline import assemble_baseline
from lab_generate_skill.domain.construction import AttemptPlanned
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import AttemptStage
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceChecks,
    assemble_equivalence,
)
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.runtime.lifecycle import OperationGuards
import state_contract_fixtures as states
import context_contract_fixtures as contexts
from construction_storage_fixtures import (
    fixture as construction_fixture,
    StorageFixture,
    put,
)
from retrieval_fixtures import reference
from test_run_journal import Harness, CancelSwitch, command


class UnitActorAdmissionAuthority:
    def __init__(self) -> None:
        self.denied = False
        self.calls = 0
        self.callback: Callable[[], None] | None = None

    def verify(
        self,
        request: ActorAdmissionRequest,
        facts: CandidateFacts,
        construction: ConstructionProgress,
        run: RunSnapshot,
    ) -> None:
        self.calls += 1
        if self.denied:
            raise OwnershipConflict("Unit actor permission denied")
        if self.callback:
            self.callback()


@dataclass
class AdmissionFixture:
    data: StorageFixture
    request: ActorAdmissionRequest
    deps: CandidateAdmissionDeps
    authority: UnitActorAdmissionAuthority
    harness: Harness
    snapshot: RunSnapshot
    inputs: EquivalenceInputs
    reader: EvidenceCandidateInputs


def fixture(
    root: Path,
    *,
    comparison_status: str = "pass",
    stage: AttemptStage = "baseline_verified",
    record_facts: bool = True,
    allowed_actions: tuple[str, ...] = ("stop",),
    shared_data: StorageFixture | None = None,
    register_attempt: bool = True,
) -> AdmissionFixture:
    data = (
        construction_fixture(root, allowed_actions=allowed_actions)
        if shared_data is None
        else shared_data
    )
    source = PublicContextReceipt.model_validate_json(
        data.store.read(data.plan.context_receipt_ref)
    )
    assert data.plan.run.owner == source.scope.owner
    construction = data.journal()
    progress = (
        construction.create(data.plan, command())
        if shared_data is None
        else construction.read(command())
    )
    event = data.event(progress)
    while not isinstance(event, AttemptPlanned):
        progress = construction.append(event, progress.revision, event.operation)
        event = data.event(progress)
    if register_attempt:
        progress = construction.append(event, progress.revision, event.operation)
    intent = event.intent
    switch = CancelSwitch()
    controls = OperationGuards(SystemClock(), switch)
    read_op = command()
    source_inputs = ContextEvidenceReader(data.store, data.context_authority).context(
        source, read_op, controls.bind(read_op)
    )

    def stored(
        value: object, schema: str = "fixture/1", visibility: str = "private"
    ) -> EvidenceRef:
        return reference(value, schema, visibility, data.store)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(states, "identity", lambda: data.plan.task.identity)
        patch.setattr(states, "reference", stored)
        patch.setattr(contexts, "reference", stored)
        candidate_inputs = contexts.candidate_inputs(
            intent.binding.attempt_id, allowed_actions=allowed_actions
        )
        checked = states.checks(source.equivalence_scope)
    if comparison_status != "pass":
        checks = (
            ()
            if comparison_status == "missing"
            else tuple(
                c.model_copy(update={"status": comparison_status})
                for c in checked.checks
            )
        )
        checked = checked.model_copy(update={"checks": checks})
    baseline = assemble_baseline(
        candidate_inputs,
        command("candidate-baseline", attempt=intent.binding.attempt_id),
    )
    baseline_ref = stored(baseline, baseline.schema_version)
    comparison = EquivalenceChecks(
        scope=baseline.scope,
        operation=command("compare", attempt=intent.binding.attempt_id),
        source_context_receipt_ref=data.plan.context_receipt_ref,
        candidate_baseline_ref=baseline_ref,
        checks=checked,
    )
    inputs = EquivalenceInputs(
        source_inputs=source_inputs,
        source=source,
        source_ref=data.plan.context_receipt_ref,
        candidate_inputs=candidate_inputs,
        candidate=baseline,
        candidate_ref=baseline_ref,
        checks=comparison,
        checks_ref=stored(comparison, comparison.schema_version),
    )
    eq = assemble_equivalence(
        inputs, command("equivalence", attempt=intent.binding.attempt_id)
    )
    context_records = EvidenceContextRecords(
        data.store, controls, data.context_authority
    )
    eq_ref = context_records.publish_equivalence(eq, eq.operation)
    skill = progress.project().candidates[intent.candidate_slot].response.skill
    skill_ref = stored(skill, "compact-skill/1", "public")
    run_plan = EvidenceRunPlans(data.store, controls).load(data.plan.run, command())
    run_root = root / "run-journal"
    run_root.mkdir()
    run_journal = FileRunJournal(
        run_root, data.plan.run, controls, data.store, capacity=run_plan.run_capacity
    )
    harness = Harness(
        run_root,
        data.store,
        run_journal,
        data.plan.run,
        data.plan.claim_ref,
        switch,
        run_plan.run_capacity,
    )
    snapshot = harness.running()
    stages = (
        "planned",
        "acquiring",
        "preparing",
        "starting",
        "baseline_verified",
        "executing",
    )
    for name in stages[: stages.index(stage) + 1]:
        entry = harness.attempt_entry(
            snapshot, intent.binding.attempt_id, cast(AttemptStage, name)
        )
        entry = entry.model_copy(update={"binding": intent.binding})
        if name == "baseline_verified" and record_facts:
            entry = entry.model_copy(
                update={
                    "event": entry.event.model_copy(
                        update={"outputs": (baseline_ref, eq_ref)}
                    )
                }
            )
        snapshot = run_journal.append(entry, snapshot.revision, entry.event.operation)
    reader = EvidenceCandidateInputs(
        data.store,
        context_records,
        EvidenceStateRecords(data.store, controls, data.context_authority),
        EvidenceObservations(data.store, controls),
        controls,
    )
    authority = UnitActorAdmissionAuthority()
    deps = CandidateAdmissionDeps(
        construction, run_journal, reader, authority, controls, data.claims()
    )
    request = ActorAdmissionRequest(
        intent=intent,
        equivalence_ref=eq_ref,
        skill_ref=skill_ref,
        operation=command("admit", attempt=intent.binding.attempt_id),
        read_operation=command("read-admission"),
    )
    return AdmissionFixture(
        data, request, deps, authority, harness, snapshot, inputs, reader
    )
