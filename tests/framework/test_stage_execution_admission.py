"""Retained real parent data and actual Slurm caller; isolated claim roots only.

No source/initialization/site/browser/model producer or production claim runs.
"""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from lab_generate_skill.adapters.ledger.source_stage_validation import (
    FileSourceStageValidations,
)
from lab_generate_skill.adapters.ledger.stage_execution_authority import (
    StageExecutionClaimAuthority,
)
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.stage_parent import RetainedStageParentChecks
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.domain.claims import SourceClaimRecord
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.execution_task_source import ExecutionTaskInputs
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.initial_equivalence import EquivalenceReceipt
from lab_generate_skill.domain.public_context import PublicContextInputs
from construction_storage_fixtures import put
from stage_admission_fixtures import retained_case, operation_controls, stage_plan
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard


@pytest.mark.parametrize("site", ["admin", "map"])
def test_retained_parent_complete_original_bodies_are_consumable(
    tmp_path: Path, site: str
) -> None:
    c = retained_case(tmp_path, site)
    op, controls, owner = operation_controls()
    target = put(c.store, {"isolated_changed_release": True}, "release-manifest/1")
    _, binding = stage_plan(c, owner, target)
    checker = c.checker(binding, target, controls)
    checker.verify_parent(checker.origin.validation, op)
    facts = checker.data(op)
    assert facts.source == c.source
    assert facts.context.scope.owner == c.parent.record.binding.run.owner
    assert facts.context.scope.owner != owner
    assert facts.authorization.binding == binding
    # Repeated consumption reuses immutable facts, not a permission decision.
    assert checker.data(op) is facts


@pytest.mark.parametrize(
    "fault", ["authorization", "caller", "source", "resource", "reset"]
)
def test_parent_rejects_missing_or_mismatched_binding(
    tmp_path: Path, fault: str
) -> None:
    c = retained_case(tmp_path)
    op, controls, owner = operation_controls()
    target = put(c.store, {"isolated_changed_release": True}, "release-manifest/1")
    _, binding = stage_plan(c, owner, target)
    checker = c.checker(binding, target, controls)
    if fault == "authorization":
        checker.authorization_id = "unselected-authorization"
    elif fault == "caller":
        op = op.model_copy(update={"run_id": "unrelated-run"})
    elif fault == "source":
        checker.origin = checker.origin.model_copy(
            update={"parent_source_ref": c.parent.reference}
        )
    elif fault == "resource":
        selected = c.evidence.model_copy(
            update={"resource_refs": c.evidence.resource_refs[:-1]}
        )
        checker = c.checker(binding, target, controls, selected=selected)
    else:
        selected = c.evidence.model_copy(
            update={"reset_refs": (c.evidence.reset_refs[0],) * 2}
        )
        with pytest.raises(ValueError):
            c.checker(binding, target, controls, selected=selected)
        return
    with pytest.raises((OwnershipConflict, ValueError)):
        checker.verify_parent(checker.origin.validation, op)


class RetainedContexts:
    def __init__(self, parent: RetainedStageParentChecks) -> None:
        self.parent = parent
        self.denied = False

    def load_context(
        self, reference: EvidenceRef, operation: OperationContext
    ) -> PublicContextReceipt:
        if self.denied:
            raise PermissionError("isolated current source revoked")
        facts = self.parent.data(operation)
        assert reference == facts.source.source_context_receipt_ref
        return facts.context

    def publish_context(
        self, receipt: PublicContextReceipt, op: OperationContext
    ) -> EvidenceRef:
        raise AssertionError("No parent publication in admission fixture")

    def publish_equivalence(
        self, receipt: EquivalenceReceipt, op: OperationContext
    ) -> EvidenceRef:
        raise AssertionError("No initialization in admission fixture")

    def load_equivalence(
        self, reference: EvidenceRef, op: OperationContext
    ) -> EquivalenceReceipt:
        raise AssertionError("Current initial equivalence is a separate stage")


@pytest.mark.parametrize("site", ["admin", "map"])
def test_actual_current_caller_stage_claim_and_revocation(
    tmp_path: Path, site: str
) -> None:
    c = retained_case(tmp_path, site)
    op, controls, owner = operation_controls()
    execution, _ = actual_slurm_execution()
    controller = observe_current_cgroup(
        execution, current_process_identity(), guard(30)
    ).membership
    owner = owner.model_copy(update={"job_id": execution.job_id})
    target = put(c.store, {"isolated_changed_release": True}, "release-manifest/1")
    run, binding = stage_plan(c, owner, target)
    parent = c.checker(binding, target, controls)
    contexts = RetainedContexts(parent)
    plans = EvidenceRunPlans(c.store, controls)
    root = c.shadow_claim_root(tmp_path / "claims")
    original = (root / c.parent.record.binding.key.filename).read_bytes()
    authority = StageExecutionClaimAuthority(
        binding.scope_id,
        binding.run,
        binding.task,
        execution,
        controller,
        evidence=c.store,
        plans=plans,
        contexts=contexts,
        controls=controls,
        parent=parent,
        claim_root=root,
    )
    authority.authorize_current(parent.origin.validation, binding, run, op)
    claims = FileSourceStageValidations(
        root,
        binding.scope_id,
        controls,
        c.store,
        plans,
        authority,
        validation=parent.origin.validation,
    )
    receipt = claims.claim(binding, op)
    assert claims.claim(binding, op) == receipt
    assert (root / c.parent.record.binding.key.filename).read_bytes() == original
    with pytest.raises(OwnershipConflict):
        authority.authorize_create(binding, run, op)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(
                authority.verify_current, parent.origin.validation, receipt.record, op
            ).result()
    contexts.denied = True
    with pytest.raises(PermissionError):
        authority.authorize_current(parent.origin.validation, binding, run, op)
    # Current parent authorization is read again, even with retained bodies.
    parent.authorization_id = "revoked-selection"
    with pytest.raises(OwnershipConflict):
        claims.read(binding.key, op)
    assert (root / c.parent.record.binding.key.filename).read_bytes() == original


def test_v2_target_slots_retain_parent_prefix_and_exact_replay_identity(
    tmp_path: Path,
) -> None:
    c = retained_case(tmp_path)
    _, controls, owner = operation_controls()
    targets = [put(c.store, {"changed": n}, "release-manifest/1") for n in (1, 2)]
    descriptors = []
    for n, target in enumerate(targets):
        _, binding = stage_plan(
            c, owner.model_copy(update={"run_id": "run-" + str(n)}), target
        )
        descriptors.append(c.checker(binding, target, controls).origin.validation)
    assert descriptors[0].filename != descriptors[1].filename
    assert descriptors[0].parent_prefix == descriptors[1].parent_prefix
    old = SourceStageValidation.model_validate(
        descriptors[0].model_copy(
            update={"schema_version": "source-stage-validation/1"}
        )
    )
    assert old.filename != descriptors[0].filename
