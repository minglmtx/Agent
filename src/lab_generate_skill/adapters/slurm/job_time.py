"""Single read of the actual scalar GPU job's finite controller end time.

No environment end-time fallback, inferred extension, polling or resubmission.
The original identity comes from independently verified accounting/kernel facts.
This read-only observation grants no new resource or operation authority.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from lab_generate_skill.adapters.processes.capture import require_reaped
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_job_time import SlurmJobTimeLimit
from lab_generate_skill.ports.lifecycle import Clock, OperationControl
from .allocation_codec import parse_controller_allocation, _number
from .commands import CommandCapture, CommandFailure, SlurmCommandRunner


def parse_job_time_limit(
    raw: bytes,
    execution: SlurmExecutionIdentity,
    node_id: str,
    observed_at: datetime,
) -> SlurmJobTimeLimit:
    # This existing decoder checks bounded bytes, parser version, one scalar
    # running job, UID/submit/start/restart identity, node and full GPU layout.
    parse_controller_allocation(raw, execution, node_id)
    job = json_object(raw)["jobs"][0]
    end = _number(job.get("end_time"))
    minutes = _number(job.get("time_limit"))
    try:
        controller_end = datetime.fromtimestamp(end, timezone.utc)
        hard_end = datetime.fromtimestamp(
            min(end, execution.started_at_epoch + minutes * 60), timezone.utc
        )
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError(
            "Controller end time is outside supported calendar range"
        ) from error
    return SlurmJobTimeLimit(
        execution=execution,
        node_id=node_id,
        observed_at=observed_at,
        controller_end=controller_end,
        hard_end=hard_end,
        time_limit_minutes=minutes,
    )


@dataclass(frozen=True)
class SlurmJobTimeObservation:
    limit: SlurmJobTimeLimit
    capture: CommandCapture


def observe_job_time_limit(
    execution: SlurmExecutionIdentity,
    node_id: str,
    control: OperationControl,
    clock: Clock,
    *,
    runner: SlurmCommandRunner,
) -> SlurmJobTimeObservation:
    execution = SlurmExecutionIdentity.model_validate(execution)
    control.checkpoint()
    argv = ("/usr/bin/scontrol", "show", "job", execution.job_id, "--json")
    capture = runner.run(argv, control)
    ending = require_reaped(capture)
    if (
        capture.argv != argv
        or capture.complete is not True
        or type(capture.returncode) is not int
        or capture.returncode != 0
        or ending.returncode != 0
        or ending.kill_requested
    ):
        raise CommandFailure("INVALID_JOB_TIME_QUERY_RESULT", capture)
    limit = parse_job_time_limit(capture.stdout, execution, node_id, clock.utcnow())
    control.checkpoint()
    return SlurmJobTimeObservation(limit, capture)
