"""Original acquired-resource scope for one source's local inference binding.

Trusted bootstrap supplies the resource/ledger/engine, never a wire caller.
Live generation requires original caller, original worker and acquired state.
Historical completion only checks the retained original acquisition; it need not
keep the model alive. This is not source admission or a recovery takeover grant.
"""

import hashlib
import json
import os
import threading
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.generator_step import GeneratorStepStarted
from lab_generate_skill.domain.local_generator import LocalGeneratorBinding
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from .generator_worker_client import SupervisedGeneratorEngine
from .generator_execution_evidence import read_exact
from .generator_step import same_allocation
from .generator_resource_records import check_operation
from lab_generate_skill.adapters.slurm.step_launch import generator_step_name
from lab_generate_skill.adapters.processes.wire_json import json_object


class GeneratorExecutionScope:
    def __init__(
        self,
        binding: LocalGeneratorBinding,
        spec: GeneratorResourceSpec,
        journal: ResourceJournal,
        evidence: EvidenceStore,
        engine: SupervisedGeneratorEngine,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self.binding = LocalGeneratorBinding.model_validate(binding)
        self.spec = GeneratorResourceSpec.model_validate(spec)
        self.journal, self.evidence, self.engine = journal, evidence, engine
        self.context = (os.getpid(), threading.get_ident())
        guard, installed = engine.owner_guard, engine.installed_sources
        if guard is None or installed is None:
            raise OwnershipConflict("Generator must already be acquired/configured")
        self.guard = guard
        if (
            binding.owner,
            binding.release_ref,
            binding.model_binding_ref,
            guard.controller,
        ) != (
            spec.token.owner,
            spec.release_ref,
            spec.model_binding_ref,
            spec.slurm.allocation.facts.writer,
        ):
            raise OwnershipConflict("Inference binding differs from original resource")
        if (installed.manifest_sha256, installed.executable) != (
            spec.release_ref.sha256,
            spec.python_executable,
        ):
            raise OwnershipConflict(
                "Inference installation differs from original resource"
            )
        self.access(binding, op, control)
        record = self._record(op, control)
        if record.state != "acquired":
            raise OwnershipConflict(
                "Bind inference only inside original acquired resource"
            )
        entries = [e for e in record.events if e.state == "acquired"]
        if len(entries) != 1 or len(entries[0].evidence) != 1:
            raise EvidenceIntegrityError("Original acquisition evidence is ambiguous")
        self._acquired = entries[0]
        self.acquired_ref = entries[0].evidence[0]
        raw = json_object(
            read_exact(evidence, self.acquired_ref, 16 * 1024 * 1024, control)
        )
        if (
            self.acquired_ref.content_schema,
            self.acquired_ref.visibility,
            raw.get("schema_version"),
            raw.get("kind"),
            raw.get("token"),
            raw.get("spec_sha256"),
            raw.get("owner_guard"),
            raw.get("worker"),
            raw.get("installed_sources"),
            raw.get("operation"),
        ) != (
            "generator-resource-fact/1",
            "private",
            "generator-resource-fact/1",
            "acquired",
            spec.token.model_dump(mode="json"),
            hashlib.sha256(spec.model_dump_json().encode()).hexdigest(),
            guard.model_dump(mode="json"),
            guard.worker.model_dump(mode="json"),
            installed.model_dump(mode="json"),
            entries[0].operation.model_dump(mode="json"),
        ):
            raise EvidenceIntegrityError("Original acquired fact differs from runtime")
        check_operation(spec, entries[0].operation, "execute")
        started = GeneratorStepStarted.model_validate_json(json.dumps(raw.get("step")))
        same_allocation(spec.slurm.allocation, started.allocation)
        if (
            started.controller.target.worker.writer != guard.worker
            or started.controller.target.step_name != generator_step_name(spec.token)
        ):
            raise EvidenceIntegrityError("Original acquired worker/step differs")
        self.require_original(op, control, live=True)

    def access(
        self,
        binding: LocalGeneratorBinding,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        binding, op = LocalGeneratorBinding.model_validate(
            binding
        ), OperationContext.model_validate(op)
        control.checkpoint()
        if (
            self.context != (os.getpid(), threading.get_ident())
            or binding != self.binding
            or current_process_identity() != self.guard.controller
        ):
            raise OwnershipConflict(
                "Inference scope escaped original binding/controller"
            )
        if (
            op.run_id,
            op.owner_id,
            op.attempt_id,
            op.allocation_id,
            op.recovery_ref,
        ) != (binding.owner.run_id, binding.owner.owner_id, None, None, None):
            raise OwnershipConflict("Inference needs original run-level operation")
        control.checkpoint()

    def _record(
        self, op: OperationContext, control: OperationControl
    ) -> ResourceRecord:
        # A distinct deterministic read operation keeps the original deadline
        # without rebinding its ID to a different allocation-scoped context.
        scoped = op.model_copy(
            update={
                "operation_id": "generator-resource-read-"
                + hashlib.sha256(
                    (op.model_dump_json() + self.spec.token.model_dump_json()).encode()
                ).hexdigest(),
                "allocation_id": self.spec.token.allocation_id,
                "recovery_ref": self.spec.token.recovery_ref,
            }
        )
        record = ResourceRecord.model_validate(
            self.journal.read(self.spec.token, scoped)
        )
        control.checkpoint()
        if record.token != self.spec.token:
            raise OwnershipConflict("Inference resource ledger identity differs")
        return record

    def require_original(
        self, op: OperationContext, control: OperationControl, *, live: bool
    ) -> None:
        self.access(self.binding, op, control)
        record = self._record(op, control)
        acquired = [e for e in record.events if e.state == "acquired"]
        if len(acquired) != 1 or acquired[0] != self._acquired:
            raise EvidenceIntegrityError("Original acquisition disappeared or changed")
        # The reference was fully validated at bind time; verify its exact
        # bytes still exist before a new external effect or historical use.
        read_exact(self.evidence, self.acquired_ref, 16 * 1024 * 1024, control)
        if live:
            if record.state != "acquired" or self.engine.owner_guard != self.guard:
                raise OwnershipConflict("Original Generator is no longer acquired")
            readings = KernelReadings(control)
            try:
                for expected in (self.guard.supervisor, self.guard.worker):
                    if (
                        read_process_identity(
                            readings,
                            expected.process_id,
                            self.spec.slurm.allocation.facts.execution.uid,
                        )
                        != expected
                    ):
                        raise OwnershipConflict(
                            "Original guarded model process differs"
                        )
            except BaseException as error:
                setattr(error, "kernel_capture", readings.capture())
                raise
        control.checkpoint()
