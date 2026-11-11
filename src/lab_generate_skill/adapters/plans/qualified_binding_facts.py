"""Recompute immutable binding facts; live caller permission stays outside."""

from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import ResourceOwner, OperationContext
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .state_reads import StateReads
from .baseline_evidence import BaselineEvidenceReader
from .task_bindings import TaskBindingEvidenceReader


def require_qualified_binding_facts(
    context_ref: EvidenceRef,
    contexts: ContextRecords,
    evidence: EvidenceReader,
    owner: ResourceOwner,
    binding: TaskBinding,
    public_task: PublicTask,
    private_spec: bytes,
    baseline: bytes,
    op: OperationContext,
    control: OperationControl,
) -> None:
    context = contexts.load_context(context_ref, op)
    if (context.scope.owner, context.scope.task) != (owner, binding.identity):
        raise OwnershipConflict("Source context changed original task or owner")
    receipt = StateReads(evidence).parse(
        context.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
    )
    initial = BaselineEvidenceReader(evidence).verify(receipt, control)
    bindings = TaskBindingEvidenceReader(evidence)
    actual = bindings.load(initial.prepared.task_binding_ref, control)
    if (
        receipt.scope != context.scope
        or receipt.status != "ready"
        or actual != binding
        or initial.binding != binding
        or initial.public_task != public_task
        or bindings.dependencies(binding, control)
        != (public_task, private_spec, baseline)
    ):
        raise OwnershipConflict("Task binding differs from qualified source bytes")
    control.checkpoint()
