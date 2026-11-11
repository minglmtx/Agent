"""Read the current original scalar Slurm execution; no submission or admission."""

import os
from lab_generate_skill.adapters.slurm.accounting import (
    ACCOUNTING_FORMAT,
    parse_accounting,
)
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.ports.lifecycle import OperationControl


def original_execution(
    control: OperationControl,
) -> tuple[SlurmExecutionIdentity, bytes]:
    job, cluster = os.environ["SLURM_JOB_ID"], os.environ["SLURM_CLUSTER_NAME"]
    control.checkpoint()
    capture = SlurmCommandRunner().run(
        (
            "/usr/bin/sacct",
            "--clusters=" + cluster,
            "-X",
            "-D",
            "-n",
            "-P",
            "--jobs=" + job,
            "--format=" + ACCOUNTING_FORMAT,
        ),
        control,
    )
    if not capture.complete or capture.returncode != 0:
        raise ValueError("Original running accounting query unconfirmed")
    lines = capture.stdout.decode().strip().splitlines()
    if len(lines) != 1:
        raise ValueError("Original scalar accounting execution is ambiguous")
    fields = lines[0].split("|")
    if len(fields) != 11:
        raise ValueError("Original accounting query changed its contract")
    value = SlurmExecutionIdentity(
        cluster=fields[0],
        job_id=fields[1],
        raw_job_id=fields[2],
        database_index=fields[3],
        uid=int(fields[4]),
        submitted_at_epoch=int(fields[5]),
        started_at_epoch=int(fields[6]),
        restart_count=int(fields[8]),
    )
    if (value.job_id, value.cluster, value.uid) != (
        job,
        cluster,
        os.getuid(),
    ) or parse_accounting(capture.stdout, value).state != "RUNNING":
        raise ValueError("Actual job differs from its original running execution")
    return value, capture.stdout
