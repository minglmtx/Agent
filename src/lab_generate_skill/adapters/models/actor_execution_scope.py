"""Bind Actor invocation to the original acquired resource and controller.

This verifies resource provenance only. Source, public projection and trace
admission remain mandatory external checks. Historical completion retains the
original acquisition even after closure; it never grants a new invocation.
"""

import hashlib
import json
import os
import threading
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_step import ActorStepStarted
from lab_generate_skill.domain.local_actor import LocalActorBinding
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControl
from lab_generate_skill.ports.actor_acquisition_inputs import ActorAcquisitionReads
from lab_generate_skill.domain.actor_acquisition_inputs import (
    ActorAcquisitionInputs,
    ActorAcquisitionBodies,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from lab_generate_skill.adapters.slurm.step_launch import actor_step_name
from .actor_worker_client import SupervisedActorEngine
from .local_actor_evidence import ActorEvidence
from .actor_step import same_allocation
from .actor_resource_records import check_operation


class ActorExecutionScope:
    def __init__(
        self,
        spec: ActorResourceSpec,
        journal: ResourceJournal,
        evidence: EvidenceStore,
        engine: SupervisedActorEngine,
        op: OperationContext,
        control: OperationControl,
        *,
        cleanup_seconds: int,
        acquisition_reads: ActorAcquisitionReads | None = None,
    ) -> None:
        self.spec = spec = ActorResourceSpec.model_validate(spec)
        check_operation(spec, op, "execute")
        self.journal, self.evidence, self.engine = (
            journal,
            ActorEvidence(evidence),
            engine,
        )
        self.context = (os.getpid(), threading.get_ident())
        self.acquisition_reads = acquisition_reads
        guard, installed = engine.owner_guard, engine.installed_sources
        if guard is None or installed is None:
            raise OwnershipConflict("Actor must already be acquired/configured")
        self.guard = guard
        if (
            guard.controller != spec.slurm.allocation.facts.writer
            or current_process_identity() != guard.controller
            or engine.session_id != spec.token.expected_resource_id
            or (installed.manifest_sha256, installed.executable)
            != (spec.release_ref.sha256, spec.python_executable)
        ):
            raise OwnershipConflict("Actor installation/controller/route differs")
        record = self._record(op, control)
        if record.state != "acquired":
            raise OwnershipConflict("Bind Actor only inside original acquired resource")
        intents = [e for e in record.events if e.state == "acquiring"]
        entries = [e for e in record.events if e.state == "acquired"]
        if (
            len(intents) != 1
            or len(intents[0].evidence) != 1
            or len(entries) != 1
            or len(entries[0].evidence) != 1
        ):
            raise EvidenceIntegrityError("Original Actor acquisition is ambiguous")
        self._intent, self._acquired = intents[0], entries[0]
        intent = self.evidence.read(
            intents[0].evidence[0],
            "resource-acquisition-intent/1",
            ResourceAcquisitionIntent,
            1024 * 1024,
            control,
        )
        if intent.token != spec.token or intent.operation != intents[0].operation:
            raise EvidenceIntegrityError("Original Actor acquisition intent differs")
        actual = self.evidence.read(
            intent.configuration_ref,
            "actor-resource-spec/1",
            ActorResourceSpec,
            8 * 1024 * 1024,
            control,
        )
        if actual != spec:
            raise EvidenceIntegrityError("Actor original acquisition spec differs")
        self.binding = LocalActorBinding(
            resource=spec.token,
            release_ref=spec.release_ref,
            model_binding_ref=spec.model_binding_ref,
            spec_ref=intent.configuration_ref,
            acquired_ref=entries[0].evidence[0],
            cleanup_seconds=cleanup_seconds,
        )
        raw = json_object(
            self.evidence.raw(self.binding.acquired_ref, 16 * 1024 * 1024, control)
        )
        expected = {
            "schema_version": "actor-resource-fact/1",
            "kind": "acquired",
            "token": spec.token.model_dump(mode="json"),
            "spec_sha256": self.binding.spec_ref.sha256,
            "owner_guard": guard.model_dump(mode="json"),
            "worker": guard.worker.model_dump(mode="json"),
            "installed_sources": installed.model_dump(mode="json"),
            "operation": entries[0].operation.model_dump(mode="json"),
        }
        if set(raw) != set(expected) | {"step"} or any(
            raw[k] != value for k, value in expected.items()
        ):
            raise EvidenceIntegrityError(
                "Actor original acquired fact differs from runtime"
            )
        check_operation(spec, entries[0].operation, "execute")
        started = ActorStepStarted.model_validate_json(json.dumps(raw["step"]))
        same_allocation(spec.slurm.allocation, started.allocation)
        if (
            started.controller.target.worker.writer != guard.worker
            or started.controller.target.step_name != actor_step_name(spec.token)
        ):
            raise EvidenceIntegrityError("Actor acquired worker/step differs")
        self.require_original(self.binding, op, control, live=True)

    def _record(
        self, op: OperationContext, control: OperationControl
    ) -> ResourceRecord:
        # Generation is attempt scoped, while its model is batch scoped. Never
        # rebind the original generation ID with a different context/deadline.
        scoped = OperationContext.model_validate(
            {
                **op.model_dump(),
                "operation_id": "actor-resource-read-"
                + hashlib.sha256(
                    (op.model_dump_json() + self.spec.token.model_dump_json()).encode()
                ).hexdigest(),
                "attempt_id": None,
                "allocation_id": self.spec.token.allocation_id,
                "recovery_ref": self.spec.token.recovery_ref,
            }
        )
        record = ResourceRecord.model_validate(
            self.journal.read(self.spec.token, scoped)
        )
        control.checkpoint()
        if record.token != self.spec.token:
            raise OwnershipConflict("Actor resource ledger identity differs")
        return record

    def require_original(
        self,
        binding: LocalActorBinding,
        op: OperationContext,
        control: OperationControl,
        *,
        live: bool,
    ) -> None:
        binding, op = LocalActorBinding.model_validate(
            binding
        ), OperationContext.model_validate(op)
        control.checkpoint()
        token = self.spec.token
        if (
            self.context != (os.getpid(), threading.get_ident())
            or binding != self.binding
            or current_process_identity() != self.guard.controller
            or (op.run_id, op.owner_id, op.allocation_id, op.recovery_ref)
            != (
                token.owner.run_id,
                token.owner.owner_id,
                token.allocation_id,
                token.recovery_ref,
            )
        ):
            raise OwnershipConflict("Actor scope escaped original binding/controller")
        if live and op.mode != "execute":
            raise OwnershipConflict("Actor invocation requires execute operation")
        record = self._record(op, control)
        for state, original in (
            ("acquiring", self._intent),
            ("acquired", self._acquired),
        ):
            if [e for e in record.events if e.state == state] != [original]:
                raise EvidenceIntegrityError("Actor original acquisition changed")
        selected = ActorAcquisitionInputs(
            binding=binding, intent_ref=self._intent.evidence[0]
        )
        bodies = None
        if self.acquisition_reads is not None and selected.supported():
            bodies = self.acquisition_reads.read_original(selected, op, control)
            if bodies is None:
                raise OwnershipConflict(
                    "Supported Actor acquisition proof was not returned"
                )
        if bodies is None:
            for original in (self._intent, self._acquired):
                self.evidence.raw(original.evidence[0], 16 * 1024 * 1024, control)
            self.evidence.raw(binding.spec_ref, 8 * 1024 * 1024, control)
        else:
            bodies = ActorAcquisitionBodies.model_validate(bodies)
            if bodies.selection != selected:
                raise OwnershipConflict(
                    "Actor proof changed exact original acquisition references"
                )
        if live:
            if (
                record.state != "acquired"
                or self.engine.owner_guard != self.guard
                or self.engine.session_id != token.expected_resource_id
            ):
                raise OwnershipConflict("Original Actor is no longer acquired")
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
                            "Original guarded Actor process differs"
                        )
            except BaseException as error:
                setattr(error, "kernel_capture", readings.capture())
                raise
        control.checkpoint()
