"""Recompute category private input, then delegate dynamic original authority."""

from typing import Protocol
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_bindings import TaskBindingAuthority
from .navigation_spec import CategoryNavigationSpec, CategoryNavigationInputs


class NativeCategoryLoader(Protocol):
    def __call__(
        self, raw: bytes, reference: EvidenceRef, public: PublicTask
    ) -> CategoryNavigationInputs: ...


class CategoryNavigationBindingAuthority:
    def __init__(
        self,
        reader: EvidenceReader,
        loader: NativeCategoryLoader,
        authority: TaskBindingAuthority,
    ) -> None:
        self.reader, self.loader, self.authority = reader, loader, authority

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
            binding.private_spec_ref.media_type,
        ) != ("shopping-category-navigation/1", "application/json"):
            raise ValueError("Current private Shopping category specification required")
        spec = CategoryNavigationSpec.model_validate_json(private_spec)
        if spec.model_dump_json().encode() != private_spec:
            raise EvidenceIntegrityError(
                "Canonical original category specification required"
            )
        if binding.identity != spec.task or public_task.identity != spec.task:
            raise OwnershipConflict("Category specification changed original task")
        control.checkpoint()
        raw = self.reader.read(spec.native_contract_ref, control=control)
        expected = self.loader(raw, spec.native_contract_ref, public_task)
        if expected.private_spec != spec:
            raise EvidenceIntegrityError(
                "Stored category differs from original native contract"
            )
        self.authority.verify_binding(
            binding, public_task, private_spec, baseline, op, control
        )
        control.checkpoint()
