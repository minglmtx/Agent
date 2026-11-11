"""Recompute selected source inputs, then require actual original binding rights."""

from typing import Protocol
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_bindings import TaskBindingAuthority
from .ssh_key_spec import SshKeySpec, SshKeyInputs


class NativeSshInputLoader(Protocol):
    def __call__(
        self, raw: bytes, reference: EvidenceRef, public_task: PublicTask
    ) -> SshKeyInputs: ...


class SshKeyBindingAuthority:
    def __init__(
        self,
        store: EvidenceReader,
        loader: NativeSshInputLoader,
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
        if (
            binding.private_spec_ref.content_schema,
            binding.private_spec_ref.visibility,
            binding.private_spec_ref.media_type,
        ) != ("gitlab-profile-ssh-key/1", "private", "application/json"):
            raise ValueError("Current private GitLab SSH specification required")
        spec = SshKeySpec.model_validate_json(private_spec)
        if spec.model_dump_json().encode() != private_spec:
            raise EvidenceIntegrityError(
                "Canonical original SSH specification required"
            )
        if binding.identity != spec.task or public_task.identity != spec.task:
            raise OwnershipConflict("GitLab binding changed original task identity")
        raw = self.store.read(spec.native_contract_ref, control=control)
        if self.loader(raw, spec.native_contract_ref, public_task).private_spec != spec:
            raise EvidenceIntegrityError(
                "Stored SSH specification differs from original native contract"
            )
        self.authority.verify_binding(
            binding, public_task, private_spec, baseline, op, control
        )
        control.checkpoint()
