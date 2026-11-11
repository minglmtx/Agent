"""Observe a pinned execution using accounting plus a complete per-user queue.

Successful command outputs, nonzero exits and bounded partial transport output
are persisted privately before interpretation. A failed queue query is never
treated as empty. Each call queries once; no retry, submit or cancellation.
"""

from lab_generate_skill.adapters.processes.deadline import DeadlineControl

from lab_generate_skill.ports.lifecycle import OperationControl

import base64
import json
from pathlib import Path

from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.scheduler import (
    SchedulerProbeError,
    SlurmExecutionIdentity,
    SlurmJobObservation,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import Clock, OperationControls

from .accounting import ACCOUNTING_FORMAT, parse_accounting, parse_queue
from .commands import CommandCapture, CommandFailure, SlurmCommandRunner


def _failure_captures(error: BaseException) -> list[CommandCapture]:
    if isinstance(error, CommandFailure):
        return [error.capture]
    if isinstance(error, BaseExceptionGroup):
        return [
            capture
            for child in error.exceptions
            for capture in _failure_captures(child)
        ]
    return []


class AccountingSlurmProbe:
    def __init__(
        self,
        evidence: EvidenceStore,
        controls: OperationControls,
        clock: Clock,
        runner: SlurmCommandRunner,
        *,
        sacct: Path,
        squeue: Path,
    ) -> None:
        if not sacct.is_absolute() or not squeue.is_absolute():
            raise ValueError("Slurm binaries must be explicitly pinned absolute paths")
        self._evidence, self._controls, self._clock = evidence, controls, clock
        self._runner, self._sacct, self._squeue = runner, str(sacct), str(squeue)

    def _save(
        self,
        execution: SlurmExecutionIdentity,
        op: OperationContext,
        captures: list[CommandCapture],
        reason: str | None,
        control: OperationControl,
    ) -> EvidenceRef:
        payload = {
            "schema_version": "slurm-probe/1",
            "execution": execution.model_dump(mode="json"),
            "operation": op.model_dump(mode="json"),
            "observed_at": self._clock.utcnow().isoformat(),
            "error": reason,
            "commands": [
                {
                    "argv": item.argv,
                    "returncode": item.returncode,
                    "stdout_base64": base64.b64encode(item.stdout).decode("ascii"),
                    "stderr_base64": base64.b64encode(item.stderr).decode("ascii"),
                    "complete": item.complete,
                }
                for item in captures
            ],
        }
        return self._evidence.put(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="slurm-probe/1",
                visibility="private",
                producer="slurm-accounting-probe-v1",
            ),
            control=control,
        )

    def observe(
        self, execution: SlurmExecutionIdentity, op: OperationContext
    ) -> SlurmJobObservation:
        execution = SlurmExecutionIdentity.model_validate(execution)
        op = OperationContext.model_validate(op)
        control = self._controls.bind(op)
        control.checkpoint()
        captures: list[CommandCapture] = []
        commands = (
            (
                self._sacct,
                "--clusters=" + execution.cluster,
                "-X",
                "-D",
                "-n",
                "-P",
                "--jobs=" + execution.job_id,
                "--format=" + ACCOUNTING_FORMAT,
            ),
            (
                self._squeue,
                "--clusters=" + execution.cluster,
                "--noheader",
                "--array",
                "--user=" + str(execution.uid),
                "--format=%i|%T",
            ),
        )
        try:
            for argv in commands:
                capture = self._runner.run(argv, control)
                captures.append(capture)
                if not capture.complete or capture.returncode != 0:
                    raise CommandFailure("NONZERO_OR_INCOMPLETE", capture)
                control.checkpoint()
        except Exception as error:
            for capture in _failure_captures(error):
                if not any(existing is capture for existing in captures):
                    captures.append(capture)
            reason = getattr(error, "reason_code", "QUERY_FAILED")
            try:
                reference = self._save(
                    execution,
                    op,
                    captures,
                    reason,
                    control=DeadlineControl(5, "scheduler-diagnostic"),
                )
            except Exception as storage_error:
                raise ExceptionGroup(
                    "Scheduler query and evidence persistence failed",
                    [error, storage_error],
                ) from None
            raise SchedulerProbeError(reason, reference) from error
        reference = self._save(execution, op, captures, None, control=control)
        control.checkpoint()
        try:
            fact = parse_accounting(captures[0].stdout, execution)
            queue = parse_queue(captures[1].stdout, execution)
        except (ValueError, UnicodeError) as error:
            raise SchedulerProbeError(
                "INVALID_OR_AMBIGUOUS_FACTS", reference
            ) from error
        control.checkpoint()
        return SlurmJobObservation(
            execution=execution,
            observed_at=self._clock.utcnow(),
            accounting_state=fact.state,
            ended_at_epoch=fact.ended_at_epoch,
            exit_status=fact.exit_status,
            exit_signal=fact.exit_signal,
            queue_state=queue,
            evidence=reference,
        )
