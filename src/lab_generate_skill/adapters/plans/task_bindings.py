"""Read the actual immutable TaskBinding dependencies; no website or authority."""

from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


class TaskBindingEvidenceReader:
    def __init__(self, reader: EvidenceReader) -> None:
        self.reads = StateReads(reader)

    @staticmethod
    def check_reference(reference: EvidenceRef) -> EvidenceRef:
        reference = EvidenceRef.model_validate(reference)
        if (reference.visibility, reference.content_schema, reference.media_type) != (
            "private",
            "task-binding/1",
            "application/json",
        ):
            raise ValueError("Expected private task-binding JSON")
        return reference

    def load(self, reference: EvidenceRef, control: OperationControl) -> TaskBinding:
        reference = self.check_reference(reference)
        raw = self.reads.read(reference, control)
        json_object(raw)
        return TaskBinding.model_validate_json(raw)

    def dependencies(
        self, binding: TaskBinding, control: OperationControl
    ) -> tuple[PublicTask, bytes, bytes]:
        public, _, private, baseline = self.dependencies_with_bodies(binding, control)
        return public, private, baseline

    def dependencies_with_bodies(
        self, binding: TaskBinding, control: OperationControl
    ) -> tuple[PublicTask, bytes, bytes, bytes]:
        """Retain exact public bytes too, without another dependency read."""
        binding = TaskBinding.model_validate(binding)
        if binding.public_task_ref.media_type != "application/json":
            raise ValueError("Expected public-task JSON")
        raw = self.reads.read(binding.public_task_ref, control)
        json_object(raw)
        public = PublicTask.model_validate_json(raw)
        if public.identity != binding.identity:
            raise OwnershipConflict("Task binding differs from actual public identity")
        private = self.reads.read(binding.private_spec_ref, control)
        baseline = self.reads.read(binding.baseline_ref, control)
        control.checkpoint()
        return public, raw, private, baseline
