"""One original registered SFT worker; existing ResourceJournal owns acquisition.

No inline trainer, new request ledger, source selection, retries or takeovers.
The exact train bytes are reachable from the durable acquisition intent before
start. A configured process is not a training permit or full closure proof.
"""

from dataclasses import asdict
import json
from lab_generate_skill.domain.training_resource import (
    TrainingLaunch,
    TrainingResourceAcquired,
    TrainingResourceClosed,
    TrainingStepCleanup,
)
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.lifecycle import (
    ResourceRecord,
    ClosureReceipt,
    OperationContext,
    CleanupFailure,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    ResourceJournal,
    OperationControls,
    OperationControl,
    Clock,
)
from lab_generate_skill.ports.training_resource import TrainingResourceAuthority
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.slurm.step_launch import fixed_training_step_argv
from lab_generate_skill.adapters.slurm.cgroup_pin import PinnedUserTree, pin_user_tree
from .worker_client import SupervisedTrainingWorker
from .worker_protocol import MAX_PACKET
from .inputs import build_sft_inputs
from .resource_records import put, put_raw, phase, acknowledged, metadata
from .resource_release import verify_training_release
from . import resource_steps as steps
import hashlib
from pathlib import Path


class TrainingResourceUnconfirmed(RuntimeError):
    def __init__(
        self,
        resource: "RegisteredTrainingResource",
        primary: BaseException | None,
        errors: tuple[BaseException, ...],
    ) -> None:
        self.resource, self.primary, self.cleanup_errors = resource, primary, errors
        self.ending_ref, self.execution_ref = (
            resource.ending_ref,
            resource.execution_ref,
        )
        self.command_capture = (
            None if resource.channel is None else resource.channel.capture
        )
        super().__init__(
            "Original training resource unconfirmed; preserve all facts, no automatic relaunch"
        )


class RegisteredTrainingResource:
    def __init__(
        self,
        launch: TrainingLaunch,
        *,
        journal: ResourceJournal,
        evidence: EvidenceStore,
        controls: OperationControls,
        clock: Clock,
        authority: TrainingResourceAuthority,
        allocation_verifier: SlurmAllocationVerifier,
    ) -> None:
        if any(
            not callable(getattr(obj, name, None))
            for obj, name in [
                (journal, "register"),
                (journal, "begin_acquire"),
                (journal, "advance"),
                (evidence, "put"),
                (evidence, "read"),
                (controls, "bind"),
                (clock, "utcnow"),
                (authority, "authorize_start"),
                (authority, "authorize_training"),
                (authority, "verify_started"),
                (authority, "verify_closed"),
                (authority, "authorize_read"),
                (allocation_verifier, "observe"),
            ]
        ):
            raise ValueError(
                "Actual original resource/phase/closure dependencies required"
            )
        self.launch = TrainingLaunch.model_validate(launch)
        self.journal, self.evidence, self.controls, self.clock = (
            journal,
            evidence,
            controls,
            clock,
        )
        self.authority, self.allocation_verifier = authority, allocation_verifier
        self.state = "new"
        self.step = steps.TrainingStepState()
        self.channel: FramedProcessSession | None = None
        self.worker: SupervisedTrainingWorker | None = None
        self.pin: PinnedUserTree | None = None
        self.record: ResourceRecord | None = None
        self.owned = False
        self.launch_ref: EvidenceRef | None = None
        self.acquired_ref: EvidenceRef | None = None
        self.execution_ref: EvidenceRef | None = None
        self.reply_ref: EvidenceRef | None = None
        self.ending_ref: EvidenceRef | None = None
        self.closure: ClosureReceipt | None = None
        self.primary: BaseException | None = None
        self.close_error: TrainingResourceUnconfirmed | None = None
        self.cleanup_started = False

    def start(self, control: OperationControl) -> None:
        if self.state != "new":
            raise OwnershipConflict("Original training acquisition is single-use")
        self.state = "admitting"
        s, c, op = (
            self.launch.spec,
            self.launch.spec.configuration,
            self.launch.spec.operation,
        )
        try:
            control.checkpoint()
            self.authority.authorize_start(s, control)
            verify_training_release(s, self.evidence, control)
            a = s.slurm.allocation
            actual = self.allocation_verifier.observe(
                a.facts.execution, a.facts.writer, phase(op, "allocation")
            )
            steps.same_allocation(a, actual)
            self.channel = FramedProcessSession(
                fixed_training_step_argv(
                    c.token,
                    actual.facts.execution,
                    actual.facts.writer.node_id,
                    python_executable=c.installation.python_executable,
                    srun_executable=s.slurm.srun_executable,
                ),
                max_frame_bytes=MAX_PACKET,
                cuda_visible_devices=actual.facts.gpu.uuid,
            )
            self.worker = SupervisedTrainingWorker(
                self.channel, c.token.expected_resource_id, c
            )
            if self.worker.controller != actual.facts.writer:
                raise OwnershipConflict(
                    "Training controller differs from actual original writer"
                )
            if (
                put(self.evidence, self.launch.train, control)
                != self.launch.command_ref
            ):
                raise EvidenceIntegrityError(
                    "Original train bytes changed before acquisition"
                )
            self.launch_ref = put(self.evidence, self.launch, control)
            registered = self.journal.register(c.token, phase(op, "register"))
            if registered.token != c.token:
                raise EvidenceIntegrityError("Training registration changed allocation")
            intent = ResourceAcquisitionIntent(
                token=c.token, operation=op, configuration_ref=self.launch_ref
            )
            intent_ref = put(self.evidence, intent, control)
            acquiring = self.journal.begin_acquire(
                c.token, intent_ref, registered.revision, op
            )
            self.record = acknowledged(
                acquiring, c.token, "acquiring", op, intent_ref, registered.revision + 1
            )
            self.owned = True  # No acknowledgement above ever grants local ownership.
            control.checkpoint()
            self.step.start_attempted = True
            self.channel.start(control)
            pid = self.channel.process_id
            if pid is None:
                raise OwnershipConflict("Training launcher identity is unknown")
            self.step.launcher = steps.launcher_identity(
                pid, actual.facts.execution.uid, control
            )
            self.worker.configure(control)
            guard, installed = self.worker.guard, self.worker.installed
            if guard is None or installed is None:
                raise OwnershipConflict(
                    "Training configuration omitted actual guard/installation"
                )
            started = steps.observe_started(
                s, actual, self.step, guard.worker, self.evidence, control
            )
            self.pin = pin_user_tree(started.controller.target.worker, control)
            exchange = self.worker.exchanges[-1]
            acquired = TrainingResourceAcquired(
                launch_ref=self.launch_ref,
                guard=guard,
                installed=installed,
                step=started,
                configure_command_ref=put_raw(
                    self.evidence, exchange.command, "sft-worker-command/1", control
                ),
                configure_reply_ref=put_raw(
                    self.evidence, exchange.reply, "sft-worker-reply/1", control
                ),
            )
            self.authority.verify_started(s, acquired, control)
            self.acquired_ref = evidence_reference(
                acquired.model_dump_json().encode(), metadata("sft-resource-acquired/1")
            )
            if put(self.evidence, acquired, control) != self.acquired_ref:
                raise EvidenceIntegrityError(
                    "Original training acquisition reference changed"
                )
            acquiring = self.record
            acquired_op = phase(op, "acquired")
            self.record = acknowledged(
                self.journal.advance(
                    c.token,
                    "acquired",
                    (self.acquired_ref,),
                    acquiring.revision,
                    acquired_op,
                ),
                c.token,
                "acquired",
                acquired_op,
                self.acquired_ref,
                acquiring.revision + 1,
            )
            control.checkpoint()
            self.state = "acquired"
        except BaseException as error:
            self.primary, self.state = error, "failed"
            raise

    def invoke(self, data: LoadedDataset, control: OperationControl) -> EvidenceRef:
        if self.state != "acquired" or self.worker is None:
            raise OwnershipConflict(
                "Only the original acquired training worker may execute once"
            )
        self.state = "executing"
        error: BaseException | None = None
        try:
            s = self.launch.spec.configuration.output
            request = build_sft_inputs(s.training, data, Path(s.output_root))
            digest = hashlib.sha256(
                json.dumps(
                    request.contract, ensure_ascii=False, sort_keys=True
                ).encode()
            ).hexdigest()
            if digest != self.launch.train.contract_sha256:
                raise EvidenceIntegrityError(
                    "Original training data/complete contract changed"
                )
            self.authority.authorize_training(self.launch, data, control)
            control.checkpoint()
            self.execution_ref = self.worker.train(self.launch.train, control)
        except BaseException as primary:
            self.primary, self.state, error = primary, "failed", primary
        # Keep the actual response even if an original native publication failed.
        try:
            exchanges = self.worker.exchanges
            if exchanges and exchanges[-1].decoded.operation == "train":
                exchange = exchanges[-1]
                self.execution_ref = exchange.decoded.execution_ref
                self.reply_ref = evidence_reference(
                    exchange.reply, metadata("sft-worker-reply/1")
                )
                if (
                    put_raw(
                        self.evidence,
                        exchange.reply,
                        "sft-worker-reply/1",
                        DeadlineControl(5, "sft-response-fact"),
                    )
                    != self.reply_ref
                ):
                    raise EvidenceIntegrityError(
                        "Original training reply reference changed"
                    )
        except BaseException as storage:
            error = (
                storage
                if error is None
                else BaseExceptionGroup(
                    "Original training and response evidence failed", [error, storage]
                )
            )
            self.primary, self.state = error, "failed"
        if error is not None:
            raise error
        if self.execution_ref is None or self.reply_ref is None:
            raise EvidenceIntegrityError(
                "Training returned without exact native response evidence"
            )
        self.state = "returned"
        return self.execution_ref

    def close(self, control: OperationControl) -> ClosureReceipt:
        if self.close_error is not None:
            raise self.close_error
        if self.closure is not None:
            return self.closure
        if (
            not self.owned
            or self.channel is None
            or self.worker is None
            or self.launch_ref is None
        ):
            raise OwnershipConflict(
                "No acknowledged original acquisition; never close another resource"
            )
        if self.cleanup_started:
            raise OwnershipConflict(
                "Original training cleanup unconfirmed; no duplicate cleanup dispatch"
            )
        self.cleanup_started = True
        c, op = self.launch.spec.configuration, self.launch.spec.operation
        errors: list[BaseException] = []
        try:
            cleanup = op.cleanup(
                "sft-resource-close-"
                + hashlib.sha256(op.operation_id.encode()).hexdigest(),
                now=self.clock.utcnow(),
                seconds=min(c.output.training.cleanup_seconds, control.checkpoint()),
            )
        except BaseException as primary:
            try:
                self.channel.abort(DeadlineControl(10, "sft-clock-failed-abort"))
            except BaseException as error:
                errors.append(error)
            self.close_error = TrainingResourceUnconfirmed(self, primary, tuple(errors))
            diagnostic = (
                primary
                if not errors
                else BaseExceptionGroup(
                    "Original training clock/physical cleanup failed",
                    [primary, *errors],
                )
            )
            raise self.close_error from diagnostic
        closing = phase(cleanup, "closing")
        try:
            raw = json.dumps(
                dict(
                    schema_version="sft-resource-closing/1",
                    launch_ref=self.launch_ref.model_dump(mode="json"),
                    operation=closing.model_dump(mode="json"),
                    primary=(
                        None
                        if self.primary is None
                        else describe_error(self.primary).model_dump(mode="json")
                    ),
                ),
                sort_keys=True,
            ).encode()
            ref = put_raw(
                self.evidence,
                raw,
                "sft-resource-closing/1",
                self.controls.bind(closing),
            )
            assert self.record is not None
            before = self.record
            self.record = acknowledged(
                self.journal.advance(
                    c.token, "closing", (ref,), before.revision, closing
                ),
                c.token,
                "closing",
                closing,
                ref,
                before.revision + 1,
            )
        except BaseException as error:
            errors.append(error)
        # Physical close always has an independent bounded guard if ledger I/O
        # exhausted bookkeeping/cancellation. No foreign PID signalling exists.
        try:
            if self.worker.state in ("configured", "returned", "closed"):
                self.worker.close(DeadlineControl(10, "sft-physical-close"))
            else:
                self.channel.abort(DeadlineControl(10, "sft-physical-abort"))
        except BaseException as error:
            errors.append(error)
        termination = self.channel.capture.termination
        observed = None
        try:
            if termination is None:
                raise OwnershipConflict(
                    "Original training launcher termination missing"
                )
            observed = steps.observe_closed(
                self.launch.spec,
                self.step,
                termination,
                self.evidence,
                self.controls.bind(cleanup),
                self.pin,
            )
            handle = TrainingStepCleanup(
                start_attempted=self.step.start_attempted,
                launcher=self.step.launcher,
                target=self.step.target,
                started=self.step.started,
            )
            self.authority.verify_closed(
                self.launch.spec,
                handle,
                termination,
                observed,
                cleanup,
                self.controls.bind(cleanup),
            )
            if observed is None and (
                self.step.start_attempted or termination.state != "not_started"
            ):
                raise OwnershipConflict(
                    "Attempted training resource lacks full original tree closure"
                )
        except BaseException as error:
            errors.append(error)
        finally:
            if self.pin is not None:
                try:
                    self.pin.close()
                except BaseException as error:
                    errors.append(error)
                self.pin = None
        try:
            if termination is None:
                raise OwnershipConflict(
                    "No physical termination fact; retain original acquisition"
                )
            ending_op = phase(cleanup, "ended")
            ending = TrainingResourceClosed(
                launch_ref=self.launch_ref,
                acquired_ref=self.acquired_ref,
                execution_ref=self.execution_ref,
                reply_ref=self.reply_ref,
                step=observed,
                operation=ending_op,
                status="quarantined" if errors else "closed",
                start_attempted=self.step.start_attempted,
                launcher=self.step.launcher,
                termination=termination,
                primary_error=(
                    None if self.primary is None else type(self.primary).__name__
                ),
                cleanup_errors=tuple(type(e).__name__ for e in errors),
            )
            self.ending_ref = put(self.evidence, ending, self.controls.bind(ending_op))
            if self.record is None or self.record.state != "closing":
                raise OwnershipConflict(
                    "Original closing acknowledgement unknown; retain ending fact only"
                )
            before = self.record
            self.record = acknowledged(
                self.journal.advance(
                    c.token,
                    ending.status,
                    (self.ending_ref,),
                    before.revision,
                    ending_op,
                ),
                c.token,
                ending.status,
                ending_op,
                self.ending_ref,
                before.revision + 1,
            )
            record_ref = put(self.evidence, self.record, self.controls.bind(cleanup))
            candidate = ClosureReceipt(
                token=c.token,
                operation_id=cleanup.operation_id,
                status="unconfirmed" if errors else "closed",
                evidence=(self.ending_ref, record_ref),
                primary_error=(
                    None
                    if ending.primary_error is None
                    else CleanupFailure(
                        component_id="sft-worker",
                        reason_code=ending.primary_error,
                        evidence=(self.ending_ref,),
                    )
                ),
                cleanup_errors=tuple(
                    CleanupFailure(
                        component_id="sft-resource",
                        reason_code=name,
                        evidence=(self.ending_ref,),
                    )
                    for name in ending.cleanup_errors
                ),
            )
            if not errors:
                self.closure, self.state = candidate, "closed"
                return candidate
        except BaseException as error:
            errors.append(error)
        self.state = "quarantined"
        self.close_error = TrainingResourceUnconfirmed(
            self, self.primary, tuple(errors)
        )
        diagnostic = BaseExceptionGroup(
            "Original training resource/cleanup facts",
            ([self.primary] if self.primary is not None else []) + errors,
        )
        raise self.close_error from diagnostic
