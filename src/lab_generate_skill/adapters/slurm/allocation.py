"""Observe actual accounting/controller/device/kernel facts without admission.

All queries are read-only and single-attempt. Before/after accounting and kernel
membership must match the original identity. Production bootstrap must supply
trusted binaries/store/probe and externally supervise synchronous kernel/CAS IO.
No result grants a resource launch, model request, recovery or retry permit.
"""

from lab_generate_skill.adapters.processes.deadline import DeadlineControl

from pathlib import Path

from lab_generate_skill.adapters.processes.capture import (
    require_reaped,
    retained_capture,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.scheduler import (
    SchedulerProbeError,
    SlurmExecutionIdentity,
    SlurmJobObservation,
)
from lab_generate_skill.domain.slurm_allocation import (
    SlurmAllocationFacts,
    SlurmAllocationObservation,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import Clock, OperationControls
from lab_generate_skill.ports.scheduler import SlurmJobProbe
from .allocation_codec import parse_controller_allocation
from .allocation_evidence import save_allocation_evidence
from .commands import CommandCapture, CommandFailure, SlurmCommandRunner
from .gpu_devices import parse_gpu_device
from .kernel_capture import KernelCapture
from .linux_cgroups import observe_current_cgroup


def _running(
    observation: SlurmJobObservation, expected: SlurmExecutionIdentity
) -> SlurmJobObservation:
    observation = SlurmJobObservation.model_validate(observation)
    if (
        observation.execution != expected
        or observation.accounting_state != "RUNNING"
        or observation.queue_state != "RUNNING"
        or observation.ended_at_epoch is not None
        or observation.exit_status != 0
        or observation.exit_signal != 0
    ):
        raise ValueError("Original allocation is not running in accounting and queue")
    return observation


class SlurmAllocationVerifier:
    def __init__(
        self,
        evidence: EvidenceStore,
        controls: OperationControls,
        clock: Clock,
        probe: SlurmJobProbe,
        runner: SlurmCommandRunner,
        *,
        scontrol: Path,
        nvidia_smi: Path,
    ) -> None:
        for binary in (scontrol, nvidia_smi):
            if (
                not isinstance(binary, Path)
                or not binary.is_absolute()
                or ".." in binary.parts
            ):
                raise ValueError(
                    "Allocation query binaries must be explicit absolute paths"
                )
        self._evidence, self._controls, self._clock = evidence, controls, clock
        self._probe, self._runner = probe, runner
        self._scontrol, self._nvidia = str(scontrol), str(nvidia_smi)

    def observe(
        self,
        execution: SlurmExecutionIdentity,
        writer: ProcessIdentity,
        op: OperationContext,
    ) -> SlurmAllocationObservation:
        execution = SlurmExecutionIdentity.model_validate(execution)
        writer = ProcessIdentity.model_validate(writer)
        op = OperationContext.model_validate(op)
        control = self._controls.bind(op)
        commands: list[CommandCapture] = []
        kernels: list[KernelCapture] = []
        schedulers: list[SlurmJobObservation] = []
        stage = "initial_guard"
        reference: EvidenceRef | None = None
        try:
            control.checkpoint()
            stage = "kernel_before"
            before = observe_current_cgroup(execution, writer, control)
            kernels.append(before.capture)
            stage = "accounting_before"
            first = SlurmJobObservation.model_validate(
                self._probe.observe(execution, op)
            )
            schedulers.append(first)
            first = _running(first, execution)
            queries = (
                (self._scontrol, "show", "job", execution.job_id, "--json"),
                (self._nvidia, "-q", "-x"),
            )
            for stage, argv in zip(("controller", "gpu"), queries, strict=True):
                control.checkpoint()
                capture = self._runner.run(argv, control)
                commands.append(capture)
                ending = require_reaped(capture)
                if (
                    capture.argv != argv
                    or capture.complete is not True
                    or type(capture.returncode) is not int
                    or capture.returncode != 0
                    or ending.returncode != capture.returncode
                    or ending.kill_requested
                ):
                    raise CommandFailure("INVALID_ALLOCATION_QUERY_RESULT", capture)
                control.checkpoint()
            stage = "parse_device_and_controller"
            controller = parse_controller_allocation(
                commands[0].stdout, execution, writer.node_id
            )
            gpu = parse_gpu_device(commands[1].stdout)
            if controller.gpu_index != gpu.minor_number:
                raise ValueError(
                    "Visible physical GPU does not match the allocated IDX"
                )
            stage = "kernel_after"
            after = observe_current_cgroup(execution, writer, control)
            kernels.append(after.capture)
            if before.membership != after.membership:
                raise ValueError("Original writer containment changed during queries")
            stage = "accounting_after"
            last = SlurmJobObservation.model_validate(
                self._probe.observe(execution, op)
            )
            schedulers.append(last)
            last = _running(last, execution)
            stage = "final_facts"
            observed_at = self._clock.utcnow()
            control.checkpoint()
            facts = SlurmAllocationFacts(
                execution=execution,
                writer=writer,
                observed_at=observed_at,
                accounting_before=first,
                accounting_after=last,
                controller=controller,
                gpu=gpu,
                cgroup=after.membership,
            )
            stage = "persist_complete_observation"
            reference = save_allocation_evidence(
                self._evidence,
                execution,
                writer,
                op,
                commands,
                kernels,
                schedulers,
                "complete",
                None,
                None,
                control=control,
            )
            stage = "final_guard"
            control.checkpoint()
            return SlurmAllocationObservation(facts=facts, evidence=reference)
        except BaseException as error:
            if reference is not None:
                setattr(error, "slurm_allocation_evidence_ref", reference)
                raise
            if stage == "persist_complete_observation":
                # Storage failure may already have committed. Never write a
                # contradictory replacement or claim non-publication.
                raise
            failed_kernel = getattr(error, "slurm_kernel_capture", None)
            if isinstance(failed_kernel, KernelCapture) and not any(
                k is failed_kernel for k in kernels
            ):
                kernels.append(failed_kernel)
            failed_command = retained_capture(error)
            if failed_command is not None and not any(
                c is failed_command for c in commands
            ):
                commands.append(failed_command)
            scheduler_failure = (
                error.evidence if isinstance(error, SchedulerProbeError) else None
            )
            try:
                reference = save_allocation_evidence(
                    self._evidence,
                    execution,
                    writer,
                    op,
                    commands,
                    kernels,
                    schedulers,
                    stage,
                    error,
                    scheduler_failure,
                    control=DeadlineControl(5, "allocation-diagnostic"),
                )
            except BaseException as storage_error:
                combined = BaseExceptionGroup(
                    "Allocation observation and evidence persistence failed",
                    [error, storage_error],
                )
                known = getattr(storage_error, "slurm_allocation_evidence_ref", None)
                if known is not None:
                    setattr(combined, "slurm_allocation_evidence_ref", known)
                raise combined from None
            setattr(error, "slurm_allocation_evidence_ref", reference)
            raise
