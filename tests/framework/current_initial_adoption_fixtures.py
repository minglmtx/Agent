"""Isolated current measurements and real CAS/claim consumers; no native grant."""

from dataclasses import dataclass
from pathlib import Path
import pytest
from lab_generate_skill.adapters.plans.initial_adoption import (
    ExecutionInitialAdoptionAuthority,
)
from lab_generate_skill.adapters.plans.candidate_inputs import EvidenceCandidateInputs
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.domain.baseline import assemble_baseline
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_adoption import (
    InitialAdoptionBinding,
    InitialAdoptionInputs,
)
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceChecks,
    EquivalenceInputs,
    EquivalenceReceipt,
    assemble_equivalence,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.state_scope import StateScope
from context_storage_fixtures import UnitContextAuthority
from frozen_execution_source_fixtures import FrozenSourceCase, frozen_source_case
from retrieval_fixtures import reference
import context_contract_fixtures as contexts
import state_contract_fixtures as states


@dataclass
class CurrentInitialCase:
    original: FrozenSourceCase
    inputs: EquivalenceInputs
    receipt: EquivalenceReceipt
    live: ExecutionInitialAdoptionAuthority
    authority: UnitContextAuthority
    records: EvidenceContextRecords
    candidates: EvidenceCandidateInputs


def current_initial_case(root: Path) -> CurrentInitialCase:
    root.mkdir()
    origin = root / "origin"
    origin.mkdir()
    c = frozen_source_case(origin)
    original = c.parent.source.data
    store, controls = original.store, original.adapter.controls

    def stored(
        value: object, schema: str = "fixture/1", visibility: str = "private"
    ) -> EvidenceRef:
        return reference(value, schema, visibility, store)

    old_scope, old_op = states.scope, states.op

    def current_scope() -> StateScope:
        return old_scope().model_copy(update={"owner": c.binding.run.owner})

    def current_op(
        name: str,
        *,
        cleanup: bool = False,
        recovery: EvidenceRef | None = None,
        allocation: str | None = None,
    ) -> OperationContext:
        return old_op(
            name, cleanup=cleanup, recovery=recovery, allocation=allocation
        ).model_copy(
            update={
                "run_id": c.binding.run.owner.run_id,
                "owner_id": c.binding.run.owner.owner_id,
            }
        )

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(states, "scope", current_scope)
        patch.setattr(states, "op", current_op)
        patch.setattr(states, "reference", stored)
        patch.setattr(contexts, "reference", stored)
        candidate = contexts.candidate_inputs(
            c.plan.intent.binding.attempt_id,
            allowed_actions=original.inputs.source_inputs.context.task.allowed_actions,
        )
    baseline_op = c.plan.operation.model_copy(
        update={"operation_id": "adopt-current-baseline"}
    )
    baseline = assemble_baseline(candidate, baseline_op)
    baseline_ref = stored(baseline, baseline.schema_version)
    adoption = InitialAdoptionInputs(
        binding=InitialAdoptionBinding(
            scope=baseline.scope,
            binding=c.plan.intent.binding,
            execution_source_ref=c.source_ref,
            source_context_ref=c.source.source_context_receipt_ref,
        ),
        source=c.source,
    )
    checks = EquivalenceChecks(
        schema_version="equivalence-checks/2",
        scope=baseline.scope,
        operation=baseline_op.model_copy(
            update={"operation_id": "adopt-current-comparison"}
        ),
        source_context_receipt_ref=adoption.binding.source_context_ref,
        candidate_baseline_ref=baseline_ref,
        checks=states.checks(original.inputs.source.equivalence_scope),
        adoption=adoption.binding,
    )
    # The check dependency body is stored using the same fixture reference factory.
    for check in checks.checks.checks:
        for ref in check.evidence:
            stored({"state": check.name})
    inputs = EquivalenceInputs(
        source_inputs=original.inputs.source_inputs,
        source=original.inputs.source,
        source_ref=adoption.binding.source_context_ref,
        candidate_inputs=candidate,
        candidate=baseline,
        candidate_ref=baseline_ref,
        checks=checks,
        checks_ref=stored(checks, checks.schema_version),
        adoption=adoption,
    )
    receipt = assemble_equivalence(
        inputs,
        baseline_op.model_copy(update={"operation_id": "adopt-current-equivalence"}),
    )
    live = ExecutionInitialAdoptionAuthority(c.plan, adoption, c.reader)
    authority = UnitContextAuthority()
    records = EvidenceContextRecords(store, controls, authority, adoption_checks=live)
    candidates = EvidenceCandidateInputs(
        store,
        records,
        EvidenceStateRecords(store, controls, authority),
        EvidenceObservations(store, controls),
        controls,
    )
    return CurrentInitialCase(c, inputs, receipt, live, authority, records, candidates)
