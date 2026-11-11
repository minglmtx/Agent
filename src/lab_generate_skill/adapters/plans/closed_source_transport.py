"""One supervised readonly graph traversal instead of one child per CAS leaf.

The existing ready store is held, real storage admission is checked before and
after, and the original parent protects the fixed installed child. Every graph
read is performed again. No facts, permissions or business outcomes are cached.
"""

from lab_generate_skill.adapters.operation_progress import operation_stage
import hashlib
import os
import threading
import time
from pydantic import TypeAdapter
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    require_reaped,
    retained_capture,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.storage.managed_store import ManagedEvidenceStore
from lab_generate_skill.adapters.storage.installation_receipt import (
    check_storage_installation,
)
from lab_generate_skill.domain.closed_source_read import (
    ClosedSourceMaterial,
    ClosedSourceBindingInput,
    ClosedSourceReadCommand,
    ClosedSourcePublicationInput,
)
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.actor_acquisition_inputs import ActorAcquisitionInputs
from lab_generate_skill.domain.preparation_read import PreparationReadRequest
from lab_generate_skill.domain.baseline_read import BaselineReadRequest
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceOwner
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceError
from lab_generate_skill.ports.evidence_storage import EvidenceStorageAdmission
from lab_generate_skill.ports.lifecycle import OperationControl
from .closed_source_protocol import (
    ENTRY,
    MAX_PACKET,
    ClosedSourceReadReply,
    encode_command,
)


class ClosedSourceReadFailure(EvidenceError):
    def __init__(
        self, capture: CommandCapture | None, reply: ClosedSourceReadReply | None
    ) -> None:
        self.capture, self.reply = capture, reply
        super().__init__(
            "Original readonly source proof unconfirmed; retain child facts"
        )


class ClosedSourceReadTransport:
    def __init__(
        self,
        scope: OwnerMetadataStorageScope,
        store: ManagedEvidenceStore,
        admission: EvidenceStorageAdmission,
    ) -> None:
        self.scope = OwnerMetadataStorageScope.model_validate(scope)
        if not isinstance(store, ManagedEvidenceStore) or admission is None:
            raise TypeError("Original ready managed store and real admission required")
        self.store, self.admission = store, admission
        self.runner = ProcessRunner(max_output_bytes=MAX_PACKET)
        self.last_capture: CommandCapture | None = None
        self.last_reply: ClosedSourceReadReply | None = None
        self.quarantined = False
        self.owner_context = os.getpid(), threading.get_ident()
        self.last_request: bytes | None = None
        self.timings: list[tuple[str, float]] = []

    def read(
        self,
        material: ClosedSourceMaterial,
        control: OperationControl,
        *,
        binding: ClosedSourceBindingInput | None = None,
        publication: ClosedSourcePublicationInput | None = None,
        plan_inputs: RunPlan | None = None,
        binding_reference: EvidenceRef | None = None,
        execution_plan: TaskExecutionPlan | None = None,
        context_inputs: bool = False,
        actor_inputs: ActorAcquisitionInputs | None = None,
        preparation_read: PreparationReadRequest | None = None,
        baseline_read: BaselineReadRequest | None = None,
        current_initial_owner: ResourceOwner | None = None,
    ) -> PublicContextReceipt:
        """Readonly evidence inspection; returned original identity grants no run.

        Historical evidence may be reviewed under this actual reader's scope.
        The production ContextRecords adapter separately requires same-owner,
        same-controller and same-release source material before using this port.
        """
        if current_initial_owner is not None and (
            (preparation_read is None) == (baseline_read is None)
        ):
            raise ValueError(
                "Current initial owner is only for one preparation/baseline proof"
            )
        if type(context_inputs) is not bool:
            raise TypeError("Context inputs selector must be bool")
        material = TypeAdapter[ClosedSourceMaterial](
            ClosedSourceMaterial
        ).validate_python(material, strict=True)
        if (
            sum(
                value is not None
                for value in (
                    binding,
                    publication,
                    plan_inputs,
                    binding_reference,
                    execution_plan,
                    actor_inputs,
                    preparation_read,
                    baseline_read,
                )
            )
            + int(context_inputs)
            > 1
        ):
            raise ValueError(
                "Binding and proposed publication are distinct source checks"
            )
        if self.owner_context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Source reader left its original controller/thread")
        if self.quarantined:
            raise ClosedSourceReadFailure(self.last_capture, self.last_reply)
        self.last_capture, self.last_reply, self.last_request = None, None, None
        control.checkpoint()
        with self.store.read_scope(control) as (read, bounded):
            if (read.binding, read.config, read.controller) != (
                self.scope.binding,
                self.scope.config,
                self.scope.writer,
            ) or current_process_identity() != read.controller:
                raise OwnershipConflict(
                    "Source proof changed original metadata owner/store"
                )
            command = (
                ClosedSourceReadCommand(
                    scope=read,
                    workspace_root=self.scope.workspace_root,
                    material=material,
                    kind="context_inputs" if context_inputs else "context",
                )
                if binding is None and publication is None
                else (
                    ClosedSourceReadCommand(
                        scope=read,
                        workspace_root=self.scope.workspace_root,
                        material=material,
                        kind="publication",
                        publication=publication,
                    )
                    if publication is not None
                    else ClosedSourceReadCommand(
                        scope=read,
                        workspace_root=self.scope.workspace_root,
                        material=material,
                        kind="binding",
                        binding=binding,
                    )
                )
            )
            if plan_inputs is not None:
                command = ClosedSourceReadCommand(
                    scope=read,
                    workspace_root=self.scope.workspace_root,
                    material=material,
                    kind="plan_inputs",
                    plan_inputs=plan_inputs,
                )
            if preparation_read is not None:
                command = ClosedSourceReadCommand(
                    scope=read,
                    workspace_root=self.scope.workspace_root,
                    material=material,
                    kind="preparation_inputs",
                    preparation_read=preparation_read,
                )
            if baseline_read is not None:
                command = ClosedSourceReadCommand(
                    scope=read,
                    workspace_root=self.scope.workspace_root,
                    material=material,
                    kind="baseline_inputs",
                    baseline_read=baseline_read,
                )
            if actor_inputs is not None:
                command = ClosedSourceReadCommand(
                    scope=read,
                    workspace_root=self.scope.workspace_root,
                    material=material,
                    kind="actor_acquisition",
                    actor_inputs=actor_inputs,
                )
            if binding_reference is not None:
                command = ClosedSourceReadCommand(
                    scope=read,
                    workspace_root=self.scope.workspace_root,
                    material=material,
                    kind="binding_reference",
                    binding_reference=binding_reference,
                )
            if execution_plan is not None:
                command = ClosedSourceReadCommand(
                    schema_version="closed-source-read-command/2",
                    scope=read,
                    workspace_root=self.scope.workspace_root,
                    material=material,
                    kind="execution_source_claim",
                    execution_plan=execution_plan,
                )
            if current_initial_owner is not None:
                command = ClosedSourceReadCommand.model_validate(
                    {
                        **command.model_dump(),
                        "schema_version": "closed-source-read-command/3",
                        "current_initial_owner": current_initial_owner,
                    }
                )
            packet = encode_command(command)
            self.last_request = packet
            with operation_stage("source.storage-admission-before"):
                with operation_stage("source.storage-admission-after"):
                    self.admission.authorize_storage(
                        read.binding, read.config, read.operation, bounded
                    )
            capture: CommandCapture | None = None
            reply: ClosedSourceReadReply | None = None
            started = time.monotonic()
            try:
                with operation_stage("source.fixed-worker"):
                    capture = self.runner.run(
                        (
                            read.config.installation.python_executable,
                            "-I",
                            "-B",
                            "-m",
                            ENTRY,
                        ),
                        bounded,
                        stdin_bytes=packet,
                    )
                self.last_capture = capture
                ending = require_reaped(capture)
                if (
                    not capture.complete
                    or capture.returncode != 0
                    or not 0 < len(capture.stdout) <= MAX_PACKET
                ):
                    raise ClosedSourceReadFailure(capture, None)
                reply = ClosedSourceReadReply.model_validate_json(capture.stdout)
                self.last_reply = reply
                if (
                    reply.request_sha256 != hashlib.sha256(packet).hexdigest()
                    or reply.worker.process_id != ending.process_id
                ):
                    raise OwnershipConflict(
                        "Source read reply changed original child/request"
                    )
                if reply.error is not None:
                    raise ClosedSourceReadFailure(capture, reply)
                if (reply.context_inputs is not None) != context_inputs:
                    raise OwnershipConflict(
                        "Source proof changed requested context input graph"
                    )
                if (reply.actor_bodies is not None) != (actor_inputs is not None) or (
                    reply.actor_bodies is not None
                    and reply.actor_bodies.selection != actor_inputs
                ):
                    raise OwnershipConflict(
                        "Source proof changed requested Actor acquisition bodies"
                    )
                if reply.publication_verified != (publication is not None):
                    raise OwnershipConflict(
                        "Source proof changed its requested publication check"
                    )
                if (reply.baseline_bodies is not None) != (
                    baseline_read is not None
                ) or (
                    reply.baseline_bodies is not None
                    and reply.baseline_bodies.request != baseline_read
                ):
                    raise OwnershipConflict(
                        "Source proof changed requested baseline inputs"
                    )
                if (reply.preparation_bodies is not None) != (
                    preparation_read is not None
                ) or (
                    reply.preparation_bodies is not None
                    and reply.preparation_bodies.request != preparation_read
                ):
                    raise OwnershipConflict(
                        "Source proof changed requested preparation inputs"
                    )
                expected_plan = (
                    None
                    if plan_inputs is None
                    else hashlib.sha256(
                        plan_inputs.model_dump_json().encode()
                    ).hexdigest()
                )
                if reply.plan_inputs_sha256 != expected_plan:
                    raise OwnershipConflict(
                        "Source proof changed requested complete plan input check"
                    )
                if reply.binding_reference != binding_reference:
                    raise OwnershipConflict(
                        "Source proof changed requested task binding reference"
                    )
                if binding_reference is not None and reply.binding is None:
                    raise OwnershipConflict(
                        "Source proof omitted verified task binding"
                    )
                if (reply.binding_bodies is not None) != (
                    binding_reference is not None
                ):
                    raise OwnershipConflict(
                        "Source proof changed requested same-call binding bodies"
                    )
                if (reply.execution_source is not None) != (execution_plan is not None):
                    raise OwnershipConflict(
                        "Source proof changed requested execution source check"
                    )
                if (reply.execution_claim is not None) != (execution_plan is not None):
                    raise OwnershipConflict(
                        "Source proof omitted or added execution claim body"
                    )
                if execution_plan is not None:
                    facts = reply.execution_source
                    assert facts is not None
                    if (
                        facts.source.intent != execution_plan.intent
                        or facts.source.run != execution_plan.intent.binding.run
                        or facts.inputs.task_binding_ref
                        != execution_plan.evaluation.task_contract_ref
                        or facts.inputs.skill_ref != execution_plan.skill_ref
                        or facts.context != reply.context
                    ):
                        raise OwnershipConflict(
                            "Source proof changed original execution task plan"
                        )
                assert reply.installed_sources is not None and reply.context is not None
                check_storage_installation(
                    read.config,
                    reply.installed_sources,
                    entry_module=ENTRY,
                    required=True,
                )
                raw = reply.context.model_dump_json().encode()
                if (len(raw), hashlib.sha256(raw).hexdigest()) != (
                    material.context_ref.size_bytes,
                    material.context_ref.sha256,
                ) or (
                    binding_reference is None
                    and reply.binding != (None if binding is None else binding.binding)
                ):
                    raise OwnershipConflict(
                        "Source proof changed original complete context/binding bytes"
                    )
                after = read.operation.model_copy(
                    update={"operation_id": read.operation.operation_id + ".after"}
                )
                self.admission.authorize_storage(
                    read.binding, read.config, after, bounded
                )
                bounded.checkpoint()
                return reply.context
            except BaseException as error:
                known = capture or retained_capture(error)
                if known is not None:
                    self.last_capture = known
                if (
                    known is None
                    or known.termination is None
                    or known.termination.state != "reaped"
                ):
                    self.quarantined = True
                raise
            finally:
                self.timings.append((command.kind, time.monotonic() - started))

    def require_current(
        self, material: ClosedSourceMaterial, op: OperationContext
    ) -> None:
        material = TypeAdapter[ClosedSourceMaterial](
            ClosedSourceMaterial
        ).validate_python(material, strict=True)
        op = OperationContext.model_validate(op)
        owner = self.scope.binding.owner
        if (
            (op.run_id, op.owner_id) != (owner.run_id, owner.owner_id)
            or material.site.token.owner != owner
            or material.site.slurm.execution != self.scope.execution
            or material.site.slurm.parent.writer != self.scope.writer
            or material.site.configuration.installation
            != self.scope.config.installation
            or material.browser.configuration.installation
            != self.scope.config.installation
        ):
            raise OwnershipConflict(
                "Current source cannot retag historical owner/controller/release"
            )

    def require_stage_validation(
        self,
        material: ClosedSourceMaterial,
        validation: SourceStageValidation,
        binding: SourceClaimBinding,
        op: OperationContext,
    ) -> None:
        """Bind historical records to an explicit current read; grants no work.

        The caller separately checks actual current controller, parent admission
        and durable claim. Neither the historical material nor its scope changes.
        """
        material = TypeAdapter[ClosedSourceMaterial](
            ClosedSourceMaterial
        ).validate_python(material, strict=True)
        validation = SourceStageValidation.model_validate(validation)
        binding = SourceClaimBinding.model_validate(binding)
        op = OperationContext.model_validate(op)
        validation.require_current_binding(binding)
        parent = validation.parent.record.binding
        if (
            self.scope.binding.owner != binding.run.owner
            or self.scope.config.installation.manifest_ref != binding.run.release_ref
            or (op.run_id, op.owner_id)
            != (binding.run.owner.run_id, binding.run.owner.owner_id)
            or material.site.token.owner != parent.run.owner
            or material.site.configuration.installation.manifest_ref
            != parent.run.release_ref
            or material.browser.configuration.spec.task.identity != parent.task.identity
        ):
            raise OwnershipConflict(
                "Frozen source changed its original material or current read scope"
            )

    def check_current(
        self,
        control: OperationControl,
    ) -> None:
        """Fresh original storage gates for a same-admission immutable handoff.

        This does not verify a graph or grant effects. The original complete
        source reads still bracket the resource check in TaskStateAdmission.
        """
        if self.owner_context != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Source reader left original controller/thread")
        if self.quarantined:
            raise ClosedSourceReadFailure(self.last_capture, self.last_reply)
        control.checkpoint()
        with self.store.read_scope(control) as (read, bounded):
            if (read.binding, read.config, read.controller) != (
                self.scope.binding,
                self.scope.config,
                self.scope.writer,
            ) or current_process_identity() != read.controller:
                raise OwnershipConflict("Source handoff changed original store/owner")
            self.admission.authorize_storage(
                read.binding, read.config, read.operation, bounded
            )
            after = read.operation.model_copy(
                update={"operation_id": read.operation.operation_id + ".after"}
            )
            self.admission.authorize_storage(read.binding, read.config, after, bounded)
            bounded.checkpoint()
