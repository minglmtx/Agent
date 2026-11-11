"""Read-only task binding permission from the original closed source context.

No claim creation, site effects or execution grant. This reads the independent
closed source port, never the current execution-source reader (which itself
loads TaskBindings), so source verification cannot recurse through itself.
"""

from lab_generate_skill.adapters.plans.qualified_binding_facts import (
    require_qualified_binding_facts,
)
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.plans.task_bindings import TaskBindingEvidenceReader
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.ports.contexts import ContextRecords
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.resource_owner import OriginalRunResourceAccess


class OriginalSourceTaskBindingAuthority:
    def __init__(
        self,
        owner: OriginalRunResourceAccess,
        context_ref: EvidenceRef,
        contexts: ContextRecords,
        evidence: EvidenceReader,
    ) -> None:
        if owner is None or contexts is None or evidence is None:
            raise TypeError("Original caller, closed source and evidence are mandatory")
        self.owner, self.context_ref, self.contexts = (
            owner,
            EvidenceRef.model_validate(context_ref),
            contexts,
        )
        self.reads = StateReads(evidence)
        self.bindings = TaskBindingEvidenceReader(evidence)
        self.baselines = BaselineEvidenceReader(evidence)

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        binding, public_task, op = (
            TaskBinding.model_validate(binding),
            PublicTask.model_validate(public_task),
            OperationContext.model_validate(op),
        )
        control.checkpoint()
        self.owner.require_caller(op)
        if binding != self.owner.task:
            raise OwnershipConflict("Binding changed original source task definition")
        require_qualified_binding_facts(
            self.context_ref,
            self.contexts,
            self.reads.store,
            self.owner.run.owner,
            binding,
            public_task,
            private_spec,
            baseline,
            op,
            control,
        )
        self.owner.require_caller(op)
        control.checkpoint()
