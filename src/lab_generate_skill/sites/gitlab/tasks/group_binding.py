"""Bind original Group source bytes under the existing mandatory authority."""

from collections.abc import Callable
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_bindings import TaskBindingAuthority
from .group_spec import GroupSpec


class GroupBindingAuthority:
    def __init__(
        self,
        store: EvidenceReader,
        loader: Callable[[bytes, EvidenceRef, PublicTask], GroupSpec],
        authority: TaskBindingAuthority,
    ) -> None:
        self.store, self.loader, self.authority = store, loader, authority

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        binding = TaskBinding.model_validate(binding)
        public_task = PublicTask.model_validate(public_task)
        op = OperationContext.model_validate(op)
        ref = binding.private_spec_ref
        if (ref.content_schema, ref.visibility, ref.media_type) != (
            "gitlab-group-creation/1",
            "private",
            "application/json",
        ):
            raise ValueError("Current private Group specification required")
        spec = GroupSpec.model_validate_json(private_spec)
        if spec.model_dump_json().encode() != private_spec:
            raise EvidenceIntegrityError(
                "Canonical original Group specification required"
            )
        if binding.identity != spec.task or public_task.identity != spec.task:
            raise OwnershipConflict("Group binding changed original identity")
        raw = self.store.read(spec.native_contract_ref, control=control)
        if self.loader(raw, spec.native_contract_ref, public_task) != spec:
            raise EvidenceIntegrityError(
                "Stored Group input differs from original contract"
            )
        self.authority.verify_binding(
            binding, public_task, private_spec, baseline, op, control
        )
        control.checkpoint()
