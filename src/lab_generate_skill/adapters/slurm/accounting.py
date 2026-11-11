"""Pure parsing of explicitly formatted Slurm accounting and full user queue.

Fields are not shortened, identity is never guessed from a prefix, and duplicate
incarnations are rejected. States remain observations, not terminal permission.
"""

import re
from dataclasses import dataclass

from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity

ACCOUNTING_FORMAT = "Cluster,JobID%64,JobIDRaw%64,DBIndex,UID,Submit,Start,End,Restarts,State%64,ExitCode"
_DECIMAL = re.compile(r"0|[1-9][0-9]*")
_STATE = re.compile(r"[A-Z_]+")
_QUEUE_ID = re.compile(r"[1-9][0-9]*(?:_[0-9]+)?(?:\+[0-9]+)?")


@dataclass(frozen=True)
class AccountingFact:
    state: str
    ended_at_epoch: int | None
    exit_status: int
    exit_signal: int


def _integer(value: str) -> int:
    if len(value) > 20 or _DECIMAL.fullmatch(value) is None:
        raise ValueError("Expected exact decimal scheduler field")
    return int(value)


def parse_accounting(raw: bytes, expected: SlurmExecutionIdentity) -> AccountingFact:
    expected = SlurmExecutionIdentity.model_validate(expected)
    lines = raw.decode("utf-8", errors="strict").splitlines()
    if len(lines) != 1 or not lines[0]:
        raise ValueError("Missing or ambiguous accounting execution")
    fields = lines[0].split("|")
    if len(fields) != 11:
        raise ValueError("Unexpected accounting columns")
    (
        cluster,
        job,
        internal,
        index,
        uid,
        submit,
        start,
        end,
        restarts,
        state,
        exit_code,
    ) = fields
    actual = SlurmExecutionIdentity(
        cluster=cluster,
        job_id=job,
        raw_job_id=internal,
        database_index=index,
        uid=_integer(uid),
        submitted_at_epoch=_integer(submit),
        started_at_epoch=_integer(start),
        restart_count=_integer(restarts),
    )
    if actual != expected:
        raise ValueError("Accounting execution does not match frozen identity")
    # Slurm CANCELLED may include a cancelling UID; keep raw bytes in evidence.
    if re.fullmatch(r"CANCELLED by [0-9]+", state):
        state = "CANCELLED"
    if _STATE.fullmatch(state) is None or len(state) > 64:
        raise ValueError("Truncated or malformed accounting state")
    parts = exit_code.split(":")
    if len(parts) != 2:
        raise ValueError("Malformed exit status")
    status, sig = map(_integer, parts)
    if status > 255 or sig > 255:
        raise ValueError("Exit status outside supported range")
    ended = None if end in ("Unknown", "None", "0") else _integer(end)
    if ended is not None and not expected.started_at_epoch <= ended <= 253402300799:
        raise ValueError("End precedes execution or exceeds supported epoch")
    return AccountingFact(state, ended, status, sig)


def parse_queue(raw: bytes, expected: SlurmExecutionIdentity) -> str | None:
    expected = SlurmExecutionIdentity.model_validate(expected)
    matched: str | None = None
    seen: set[str] = set()
    for line in raw.decode("utf-8", errors="strict").splitlines():
        fields = line.split("|")
        if len(fields) != 2:
            raise ValueError("Malformed full queue row")
        job, state = fields
        if (
            _QUEUE_ID.fullmatch(job) is None
            or _STATE.fullmatch(state) is None
            or len(state) > 64
        ):
            raise ValueError("Malformed queue identity/state")
        if job in seen:
            raise ValueError("Duplicate queue row")
        seen.add(job)
        if job in (expected.job_id, expected.raw_job_id):
            if matched is not None:
                raise ValueError("Ambiguous aliases in current queue")
            matched = state
    return matched
