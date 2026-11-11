"""Controlled task-definition CAS transport; immutable bytes, no site effects.

Dependencies must already exist. Publication reads them and invokes the required
semantic authority before its sole put. Partial dependency publications belong
to their producer; this adapter never deletes, initializes or retries them.
"""

import hashlib
from lab_generate_skill.adapters.plans.task_bindings import TaskBindingEvidenceReader
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_publication import (
    TaskBindingCommitUnconfirmed,
    TaskBindingInputs,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.task_bindings import (
    TaskBindingAuthority,
    TaskBindingLoadChecks,
    TaskBindingInputLoadChecks,
)


class EvidenceTaskBindings:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        authority: TaskBindingAuthority,
        *,
        load_checks: TaskBindingLoadChecks | None = None,
    ) -> None:
        self.store, self.controls, self.authority = store, controls, authority
        self.reader = TaskBindingEvidenceReader(store)
        self.load_checks = load_checks

    def _verify(
        self, binding: TaskBinding, op: OperationContext, control: OperationControl
    ) -> TaskBindingInputs:
        public, private, baseline = self.reader.dependencies(binding, control)
        self.authority.verify_binding(binding, public, private, baseline, op, control)
        control.checkpoint()
        return TaskBindingInputs(binding, public, private, baseline)

    @property
    def loads_inputs_in_one_call(self) -> bool:
        return self.load_checks is None or isinstance(
            self.load_checks, TaskBindingInputLoadChecks
        )

    def load_inputs(
        self, reference: EvidenceRef, op: OperationContext
    ) -> TaskBindingInputs:
        if not self.loads_inputs_in_one_call:
            raise ValueError(
                "Supervised binding checks retain their original graph path"
            )
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        control.checkpoint()
        if self.load_checks is None:
            binding = self.reader.load(reference, control)
            result = self._verify(binding, op, control)
        else:
            assert isinstance(self.load_checks, TaskBindingInputLoadChecks)
            reference = self.reader.check_reference(reference)
            result = self.load_checks.load_binding_inputs(reference, op, control)
            if not isinstance(result, TaskBindingInputs):
                raise TypeError("Supervised task input proof returned no typed bodies")
        control.checkpoint()
        return result

    def publish(self, binding: TaskBinding, op: OperationContext) -> EvidenceRef:
        binding = TaskBinding.model_validate(binding)
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        control.checkpoint()
        self._verify(binding, op, control)
        raw = binding.model_dump_json().encode()
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema="task-binding/1",
            visibility="private",
            producer="task-bindings-v1",
        )
        reference = EvidenceRef.model_validate(
            self.store.put(raw, metadata, control=control)
        )
        if (
            reference.sha256,
            reference.size_bytes,
            reference.media_type,
            reference.content_schema,
            reference.visibility,
            reference.producer,
        ) != (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
            metadata.media_type,
            metadata.content_schema,
            metadata.visibility,
            metadata.producer,
        ):
            raise EvidenceIntegrityError(
                "Store returned a different task binding reference"
            )
        try:
            control.checkpoint()
        except Exception as error:
            raise TaskBindingCommitUnconfirmed(reference) from error
        return reference

    def load(self, reference: EvidenceRef, op: OperationContext) -> TaskBinding:
        op = OperationContext.model_validate(op)
        control = self.controls.bind(op)
        control.checkpoint()
        reference = self.reader.check_reference(reference)
        if self.load_checks is None:
            binding = self.reader.load(reference, control)
            self._verify(binding, op, control)
        else:
            binding = TaskBinding.model_validate(
                self.load_checks.load_binding(reference, op, control)
            )
        control.checkpoint()
        return binding
