"""Fixed installed readonly whole-graph proof under original parent protection.

Every invocation reopens and verifies the full graph. No cache, model, website,
CAS write, claim, continuation, runner, journal or dynamic executable exists here.
The logical record scope never substitutes for the actual protected controller.
"""

import hashlib
import os
from pathlib import Path
import resource
import sys
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.evidence import (
    check_run_plan_input_evidence,
    EvidenceRunPlans,
)
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.plans.claim_evidence import ClaimEvidence
from lab_generate_skill.domain.claims import SourceClaimReceipt, check_source_claim
from lab_generate_skill.domain.execution_task_source import (
    ExecutionTaskSource,
    ExecutionTaskInputs,
    check_execution_source_facts,
    execution_context_owner,
)
from lab_generate_skill.domain.run_plan import ExecutionWorkload
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.closed_source_read import ClosedSourceMaterial
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.execution_task_source import ExecutionSourceFacts
from lab_generate_skill.ports.contexts import ContextRecords, ContextFactReads
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.plans.task_bindings import TaskBindingEvidenceReader
from lab_generate_skill.adapters.plans.closed_source_protocol import (
    decode_command,
    encode_reply,
    ClosedSourceReadReply,
    ClosedSourceBindingBodies,
    MAX_PACKET,
)
from lab_generate_skill.adapters.plans.qualified_binding_facts import (
    require_qualified_binding_facts,
)
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.storage.readonly_session import (
    ReadOnlySessionAuthority,
)
from lab_generate_skill.adapters.ledger.evidence_sessions import FileEvidenceSessions
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner, ended
from lab_generate_skill.adapters.processes.owner_supervisor import arm_parent_death
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.releases.installation import (
    verify_release_installation,
)
from lab_generate_skill.domain.lifecycle import OperationContext, CancellationRef
from lab_generate_skill.domain.release_installation import InstalledReleaseSources
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.runtime.lifecycle import OperationGuards
from .closed_source_read_bindings import bind_closed_source_read


def read_execution_source_facts(
    plan: TaskExecutionPlan,
    material: ClosedSourceMaterial,
    evidence: ReadOnlyEvidence,
    controls: OperationControls,
    reader: ContextRecords,
    op: OperationContext,
    context: PublicContextReceipt,
    control: OperationControl,
    *,
    current_operation: OperationContext | None = None,
) -> ExecutionSourceFacts:
    # The same installed reader and original algorithms validate all
    # immutable dependencies in one fresh proof. Live claim/caller
    # permission remains in the parent, before any side effect.
    plan = TaskExecutionPlan.model_validate(plan)
    assert plan.source_ref is not None
    reads = StateReads(evidence)
    source = reads.parse(
        plan.source_ref, plan.source_ref.content_schema, ExecutionTaskSource, control
    )
    parent_source = None
    if source.frozen_origin is not None:
        parent_source = reads.parse(
            source.frozen_origin.parent_source_ref,
            "execution-task-source/1",
            ExecutionTaskSource,
            control,
        )
    context_owner = execution_context_owner(source, parent_source)
    origin_run = source.run if parent_source is None else parent_source.run
    if (
        source.intent != plan.intent
        or source.run != plan.intent.binding.run
        or context_owner != material.site.token.owner
        or origin_run.release_ref
        != material.site.configuration.installation.manifest_ref
        or source.task.identity != material.browser.configuration.spec.task.identity
        or source.source_context_receipt_ref != material.context_ref
    ):
        raise OwnershipConflict("Execution proof changed original source/task/release")
    plan_op = op
    if source.frozen_origin is not None:
        if current_operation is None:
            raise OwnershipConflict(
                "Frozen source proof requires its actual current read scope"
            )
        plan_op = current_operation
    run = EvidenceRunPlans(evidence, controls).load(source.run, plan_op)
    if not isinstance(run.workload, ExecutionWorkload):
        raise OwnershipConflict("Original execution workload required")
    inputs = reads.parse(
        run.workload.task_inputs_ref,
        "execution-task-inputs/1",
        ExecutionTaskInputs,
        control,
    )
    policy = reads.parse(
        run.workload.execution_policy_ref,
        "engineering-execution-policy/3",
        EngineeringActorPolicy,
        control,
    )
    tasks = TaskBindingEvidenceReader(evidence)
    task = tasks.load(inputs.task_binding_ref, control)
    public, private, baseline = tasks.dependencies(task, control)
    require_qualified_binding_facts(
        material.context_ref,
        reader,
        evidence,
        context_owner,
        task,
        public,
        private,
        baseline,
        op,
        control,
    )
    facts = check_execution_source_facts(
        source,
        inputs,
        run,
        policy,
        task,
        public,
        context,
        skill=reads.read(inputs.skill_ref, control),
        parent_source=parent_source,
    )
    if (
        inputs.task_binding_ref != plan.evaluation.task_contract_ref
        or inputs.skill_ref != plan.skill_ref
    ):
        raise OwnershipConflict("Execution proof changed frozen evaluation/skill")
    return facts


def serve(raw: bytes, controls: OperationControls) -> bytes:
    command = decode_command(raw)
    scope, m = command.scope, command.material
    control = controls.bind(scope.operation)
    worker = current_process_identity()
    installed: InstalledReleaseSources | None = None
    context: PublicContextReceipt | None = None
    binding: TaskBinding | None = None
    error = None
    plan_inputs_sha256 = None
    binding_reference = None
    binding_bodies = None
    execution_source = None
    execution_claim = None
    context_inputs = None
    actor_bodies = None
    preparation_bodies = None
    baseline_bodies = None
    original: ReadOnlyEvidence | None = None
    try:
        control.checkpoint()
        if os.getppid() != scope.controller.process_id:
            raise OwnershipConflict("Source proof controller is not the actual parent")
        with pinned_owner(scope.controller, control) as parent:
            arm_parent_death(scope.controller.process_id)
            installed = verify_release_installation(scope.config.installation, control)
            session = FileEvidenceSessions(
                Path(scope.config.session_root),
                scope.config.storage_id,
                scope.config.sha256,
                controls,
                ReadOnlySessionAuthority(scope, worker, parent, control),
            )
            before = session.read(scope.binding, scope.operation)
            if (
                before.revision != scope.revision
                or before.capacity != scope.config.capacity
                or (before.entries and not before.entries[-1].reusable)
            ):
                raise OwnershipConflict(
                    "Original evidence namespace is stale or unresolved"
                )
            root = Path(scope.config.evidence_root)
            workspace = Path(command.workspace_root)
            if (
                root.resolve(strict=True) != root
                or not root.is_dir()
                or root == workspace
                or not root.is_relative_to(workspace)
            ):
                raise OwnershipConflict(
                    "Source proof root is not canonical in original workspace"
                )
            original = ReadOnlyEvidence(
                root,
                max_object_bytes=scope.config.max_object_bytes,
                proposed=command.publication,
                reuse_within_proof=True,
            )
            evidence = original
            # Only the retained-record identity is selected here. The actual
            # process/controller and admission remain scope.controller/binding.
            op = OperationContext(
                operation_id=scope.operation.operation_id + ".records",
                run_id=m.site.token.owner.run_id,
                owner_id=m.site.token.owner.owner_id,
                deadline=scope.operation.deadline,
            )
            selected = bind_closed_source_read(m)
            if command.publication is not None:
                # Execute the original publishers' complete validation and
                # writing guards against proposed bytes only. Their _put has
                # no physical capability here; the actual parent publishes
                # only after this checked installed child has been reaped.
                proposed = command.publication
                if proposed.context.scope.owner != m.site.token.owner:
                    raise OwnershipConflict(
                        "Proposed publication changed original source owner"
                    )
                initial = BaselineEvidenceReader(evidence).verify(
                    proposed.baseline, control
                )
                authority = selected.authority(
                    proposed.context,
                    initial,
                    evidence,
                    controls,
                    op,
                )
                states = EvidenceStateRecords(evidence, controls, authority)
                contexts = EvidenceContextRecords(evidence, controls, authority)

                def reconciliation(
                    original_op: OperationContext, name: str
                ) -> OperationContext:
                    return original_op.cleanup(
                        scope.operation.operation_id + name,
                        now=SystemClock().utcnow(),
                        seconds=control.checkpoint(),
                    ).model_copy(update={"deadline": scope.operation.deadline})

                if (
                    states.publish_baseline(
                        proposed.baseline,
                        reconciliation(proposed.baseline.operation, ".baseline"),
                    )
                    != proposed.context.baseline_ref
                ):
                    raise OwnershipConflict(
                        "Proposed baseline validation returned another reference"
                    )
                if (
                    states.publish_reset(
                        proposed.reset,
                        reconciliation(proposed.reset.operation, ".reset"),
                    )
                    != proposed.context.reset_ref
                ):
                    raise OwnershipConflict(
                        "Proposed Reset validation returned another reference"
                    )
                if (
                    contexts.publish_context(
                        proposed.context,
                        reconciliation(proposed.context.operation, ".context"),
                    )
                    != m.context_ref
                ):
                    raise OwnershipConflict(
                        "Proposed context validation returned another reference"
                    )
            reader = selected.contexts(evidence, controls, op)
            if command.kind == "context_inputs":
                if not isinstance(reader, ContextFactReads):
                    raise TypeError("Original full context reader required")
                result, context_inputs = reader.load_context_inputs(m.context_ref, op)
            else:
                result = reader.load_context(m.context_ref, op)
            if command.binding is not None:
                b = command.binding
                require_qualified_binding_facts(
                    m.context_ref,
                    reader,
                    evidence,
                    m.site.token.owner,
                    b.binding,
                    b.public_task,
                    b.private_spec_json.encode(),
                    b.baseline_json.encode(),
                    op,
                    control,
                )
                binding = b.binding
            if command.binding_reference is not None:
                tasks = TaskBindingEvidenceReader(evidence)
                task = tasks.load(command.binding_reference, control)
                public, public_raw, private, baseline = tasks.dependencies_with_bodies(
                    task, control
                )
                require_qualified_binding_facts(
                    m.context_ref,
                    reader,
                    evidence,
                    m.site.token.owner,
                    task,
                    public,
                    private,
                    baseline,
                    op,
                    control,
                )
                binding = task
                binding_reference = command.binding_reference
                binding_bodies = ClosedSourceBindingBodies(
                    binding=task,
                    public_task_json=public_raw.decode(),
                    private_spec_json=private.decode(),
                    baseline_json=baseline.decode(),
                )
            if command.preparation_read is not None:
                from lab_generate_skill.adapters.plans.preparation_read import (
                    read_preparation_inputs,
                )

                preparation_bodies = read_preparation_inputs(
                    command.preparation_read,
                    m,
                    reader,
                    evidence,
                    controls,
                    control,
                    op,
                    current_initial_owner=command.current_initial_owner,
                )
            if command.baseline_read is not None:
                from lab_generate_skill.adapters.plans.baseline_read import (
                    read_baseline_inputs,
                )

                baseline_bodies = read_baseline_inputs(
                    command.baseline_read,
                    m,
                    reader,
                    evidence,
                    control,
                    op,
                    current_initial_owner=command.current_initial_owner,
                )
            if command.actor_inputs is not None:
                from lab_generate_skill.domain.actor_acquisition_inputs import (
                    ActorAcquisitionBodies,
                )

                actor_selected = command.actor_inputs
                actor_bodies = ActorAcquisitionBodies(
                    selection=actor_selected,
                    intent_json=evidence.read(
                        actor_selected.intent_ref, control=control
                    ).decode(),
                    spec_json=evidence.read(
                        actor_selected.binding.spec_ref, control=control
                    ).decode(),
                    acquired_json=evidence.read(
                        actor_selected.binding.acquired_ref, control=control
                    ).decode(),
                )
            if command.plan_inputs is not None:
                plan = command.plan_inputs
                if (
                    plan.run_id != m.site.token.owner.run_id
                    or plan.release_ref
                    != m.site.configuration.installation.manifest_ref
                    or tuple(task.identity for task in plan.tasks)
                    != (m.browser.configuration.spec.task.identity,)
                ):
                    raise OwnershipConflict(
                        "Plan inputs changed original owner/release/task"
                    )
                check_run_plan_input_evidence(plan, evidence, control)
                plan_inputs_sha256 = hashlib.sha256(
                    plan.model_dump_json().encode()
                ).hexdigest()
            if command.execution_plan is not None:
                execution_source = read_execution_source_facts(
                    command.execution_plan,
                    m,
                    evidence,
                    controls,
                    reader,
                    op,
                    result,
                    control,
                    current_operation=scope.operation,
                )
                if command.kind == "execution_source_claim":
                    source = execution_source.source
                    ref = source.intent.binding.claim_ref
                    record = ClaimEvidence(
                        evidence, EvidenceRunPlans(evidence, controls)
                    ).load(ref, control)
                    check_source_claim(record, ref, source.run, source.task)
                    execution_claim = SourceClaimReceipt(record=record, reference=ref)
            control.checkpoint()
            if session.read(scope.binding, scope.operation) != before:
                raise OwnershipConflict(
                    "Original evidence namespace changed during readonly proof"
                )
            if ended(parent) or os.getppid() != scope.controller.process_id:
                raise OwnershipConflict("Original controller ended during source proof")
            context = result
        control.checkpoint()
    except BaseException as caught:
        context, binding, plan_inputs_sha256, binding_reference = None, None, None, None
        execution_source = None
        execution_claim = None
        context_inputs = None
        binding_bodies = None
        actor_bodies = None
        preparation_bodies = None
        baseline_bodies = None
        error = describe_error(caught)
    return encode_reply(
        ClosedSourceReadReply(
            schema_version=(
                "closed-source-read-reply/6"
                if execution_claim is not None
                else (
                    "closed-source-read-reply/5"
                    if baseline_bodies is not None
                    else (
                        "closed-source-read-reply/4"
                        if preparation_bodies is not None
                        else (
                            "closed-source-read-reply/3"
                            if actor_bodies is not None
                            else (
                                "closed-source-read-reply/2"
                                if binding_bodies is not None
                                else "closed-source-read-reply/1"
                            )
                        )
                    )
                )
            ),
            request_sha256=hashlib.sha256(raw).hexdigest(),
            worker=worker,
            installed_sources=installed,
            context=context,
            binding=binding,
            error=error,
            publication_verified=error is None and command.publication is not None,
            read_count=0 if original is None else original.read_count,
            body_read_count=0 if original is None else original.body_read_count,
            unique_objects=0 if original is None else len(original.unique_objects),
            plan_inputs_sha256=plan_inputs_sha256,
            binding_reference=binding_reference,
            binding_bodies=binding_bodies,
            execution_source=execution_source,
            execution_claim=execution_claim,
            context_inputs=context_inputs,
            actor_bodies=actor_bodies,
            preparation_bodies=preparation_bodies,
            baseline_bodies=baseline_bodies,
        )
    )


class NoPrivateCancellation:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        raise ValueError(
            "Private source read delegates cancellation to its original parent"
        )


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        raw = sys.stdin.buffer.read(MAX_PACKET + 1)
        reply = serve(raw, OperationGuards(SystemClock(), NoPrivateCancellation()))
        sys.stdout.buffer.write(reply)
        sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("CLOSED_SOURCE_READ_PROTOCOL_OR_OUTPUT_FAILED\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
