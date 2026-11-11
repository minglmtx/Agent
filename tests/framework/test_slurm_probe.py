"""Exact scheduler identity and retained evidence; no termination permission."""

import base64
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.slurm.accounting import parse_accounting, parse_queue
from lab_generate_skill.adapters.slurm.commands import (
    CommandCapture,
    CommandFailure,
    SlurmCommandRunner,
)
from lab_generate_skill.adapters.slurm.probe import AccountingSlurmProbe
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.lifecycle import CancellationRef, OperationContext
from lab_generate_skill.domain.scheduler import (
    SchedulerProbeError,
    SlurmExecutionIdentity,
    SlurmJobObservation,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.scheduler import SlurmJobProbe
from lab_generate_skill.runtime.lifecycle import OperationGuards


def execution(**changes: object) -> SlurmExecutionIdentity:
    values: dict[str, object] = dict(
        cluster="alex",
        job_id="123",
        raw_job_id="123",
        database_index="999",
        uid=1000,
        submitted_at_epoch=1700000000,
        started_at_epoch=1700000001,
        restart_count=0,
    )
    values.update(changes)
    return SlurmExecutionIdentity.model_validate(values)


def accounting(
    identity: SlurmExecutionIdentity | None = None, /, **changes: str
) -> bytes:
    item = identity or execution()
    fields = dict(
        cluster=item.cluster,
        job=item.job_id,
        raw=item.raw_job_id,
        db=item.database_index,
        uid=str(item.uid),
        submit=str(item.submitted_at_epoch),
        start=str(item.started_at_epoch),
        end=str(item.started_at_epoch + 10),
        restarts=str(item.restart_count),
        state="COMPLETED",
        exit="0:0",
    )
    fields.update(changes)
    return ("|".join(fields.values()) + "\n").encode()


class NoCancel:
    def is_cancelled(self, ref: CancellationRef) -> bool:
        return False


def operation() -> OperationContext:
    return OperationContext(
        operation_id="probe-" + uuid4().hex,
        run_id="run",
        owner_id="owner",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
    )


class ScriptedRunner(SlurmCommandRunner):
    def __init__(self, results: Sequence[tuple[int, bytes, bytes] | Exception]) -> None:
        super().__init__()
        self.results = list(results)
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], control: OperationControl) -> CommandCapture:
        control.checkpoint()
        self.calls.append(argv)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        code, out, err = result
        return CommandCapture(argv, code, out, err, True)


@dataclass
class Harness:
    store: FileEvidenceStore
    controls: OperationGuards

    def probe(
        self, runner: SlurmCommandRunner, store: EvidenceStore | None = None
    ) -> SlurmJobProbe:
        return AccountingSlurmProbe(
            store or self.store,
            self.controls,
            SystemClock(),
            runner,
            sacct=Path("/usr/bin/sacct"),
            squeue=Path("/usr/bin/squeue"),
        )


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(
        FileEvidenceStore(tmp_path), OperationGuards(SystemClock(), NoCancel())
    )


def test_observation_roundtrip_retains_raw_commands(harness: Harness) -> None:
    runner = ScriptedRunner(
        [(0, accounting(), b"warning\n"), (0, b"456|RUNNING\n", b"")]
    )
    result = harness.probe(runner).observe(execution(), operation())
    assert result.accounting_state == "COMPLETED" and result.queue_state is None
    assert SlurmJobObservation.model_validate_json(result.model_dump_json()) == result
    raw = json.loads(harness.store.read(result.evidence))
    assert raw["schema_version"] == "slurm-probe/1" and raw["error"] is None
    assert base64.b64decode(raw["commands"][0]["stdout_base64"]) == accounting()
    assert base64.b64decode(raw["commands"][0]["stderr_base64"]) == b"warning\n"
    assert len(runner.calls) == 2
    assert "-D" in runner.calls[0] and "-X" in runner.calls[0]
    assert "--clusters=alex" in runner.calls[0] and "--clusters=alex" in runner.calls[1]
    assert "--user=1000" in runner.calls[1] and "--array" in runner.calls[1]
    assert not any(arg.startswith("--jobs=") for arg in runner.calls[1])
    assert not hasattr(result, "descendants_terminated")


@pytest.mark.parametrize(
    "state",
    [
        "RUNNING",
        "COMPLETING",
        "NODE_FAIL",
        "FAILED",
        "TIMEOUT",
        "PREEMPTED",
        "UNKNOWN_FUTURE_STATE",
    ],
)
def test_states_are_facts_never_permission(harness: Harness, state: str) -> None:
    runner = ScriptedRunner(
        [(0, accounting(state=state), b""), (0, b"123|COMPLETING\n", b"")]
    )
    result = harness.probe(runner).observe(execution(), operation())
    assert result.accounting_state == state and result.queue_state == "COMPLETING"


def test_completed_accounting_and_live_queue_both_retained(harness: Harness) -> None:
    runner = ScriptedRunner([(0, accounting(), b""), (0, b"123|RUNNING\n", b"")])
    result = harness.probe(runner).observe(execution(), operation())
    assert result.accounting_state == "COMPLETED" and result.queue_state == "RUNNING"


@pytest.mark.parametrize(
    "field,value",
    [
        ("cluster", "elsewhere"),
        ("job", "124"),
        ("raw", "124"),
        ("db", "1000"),
        ("uid", "1001"),
        ("submit", "1699999999"),
        ("start", "1700000002"),
        ("restarts", "1"),
    ],
)
def test_identity_mismatch_rejected(harness: Harness, field: str, value: str) -> None:
    runner = ScriptedRunner([(0, accounting(**{field: value}), b""), (0, b"", b"")])
    with pytest.raises(SchedulerProbeError) as caught:
        harness.probe(runner).observe(execution(), operation())
    assert caught.value.reason_code == "INVALID_OR_AMBIGUOUS_FACTS"
    assert len(json.loads(harness.store.read(caught.value.evidence))["commands"]) == 2


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\n",
        b"bad",
        b"\xff",
        accounting() + accounting(),
        accounting() + b"\n",
        accounting(state="COMPLETED+"),
        accounting(end="1699999999"),
        accounting(uid="True"),
        accounting(start="Unknown"),
        accounting(exit="1"),
        accounting(exit="256:0"),
        accounting(exit="0:-1"),
        accounting(restarts="1.0"),
        accounting(end="253402300800"),
        accounting() + b"unexpected warning\n",
    ],
)
def test_bad_accounting_rejected(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_accounting(raw, execution())


def test_cancelled_suffix_and_absent_end() -> None:
    assert (
        parse_accounting(accounting(state="CANCELLED by 1000"), execution()).state
        == "CANCELLED"
    )
    for end in ("Unknown", "None", "0"):
        assert (
            parse_accounting(
                accounting(end=end, state="RUNNING"), execution()
            ).ended_at_epoch
            is None
        )


@pytest.mark.parametrize(
    "raw",
    [
        b"\n",
        b"\xff",
        b"123",
        b"123|RUNNING|extra\n",
        b"123|RUNNING+\n",
        b"123|RUNNING\n123|PENDING\n",
        b"123_[1-9]|RUNNING\n",
        b"CLUSTER: alex\n",
        b"123|\n",
    ],
)
def test_bad_queue_never_means_absent(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_queue(raw, execution())


def test_array_aliases_are_exact() -> None:
    item = execution(job_id="120_3", raw_job_id="123")
    assert parse_accounting(accounting(item), item).state == "COMPLETED"
    assert parse_queue(b"120_4|RUNNING\n120_30|RUNNING\n", item) is None
    assert parse_queue(b"120_3|RUNNING\n", item) == "RUNNING"
    assert parse_queue(b"123|RUNNING\n", item) == "RUNNING"
    with pytest.raises(ValueError):
        parse_queue(b"123|RUNNING\n120_3|RUNNING\n", item)
    with pytest.raises(ValueError):
        parse_accounting(accounting(execution(job_id="120_4", raw_job_id="124")), item)


@pytest.mark.parametrize("stage", [0, 1])
def test_nonzero_is_not_empty_and_not_retried(harness: Harness, stage: int) -> None:
    rows = [(0, accounting(), b"")] * stage + [(1, b"", b"scheduler unavailable")]
    runner = ScriptedRunner(rows)
    with pytest.raises(SchedulerProbeError) as caught:
        harness.probe(runner).observe(execution(), operation())
    assert len(runner.calls) == stage + 1
    data = json.loads(harness.store.read(caught.value.evidence))
    assert data["commands"][-1]["returncode"] == 1
    assert (
        base64.b64decode(data["commands"][-1]["stderr_base64"])
        == b"scheduler unavailable"
    )


def test_partial_transport_output_persisted(harness: Harness) -> None:
    capture = CommandCapture(("/usr/bin/sacct",), None, b"partial", b"", False)
    runner = ScriptedRunner([CommandFailure("DEADLINE_EXCEEDED", capture)])
    with pytest.raises(SchedulerProbeError) as caught:
        harness.probe(runner).observe(execution(), operation())
    assert caught.value.reason_code == "DEADLINE_EXCEEDED"
    raw = json.loads(harness.store.read(caught.value.evidence))
    assert raw["commands"][0]["complete"] is False
    assert base64.b64decode(raw["commands"][0]["stdout_base64"]) == b"partial"


class BrokenStore:
    def put(
        self, payload: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        raise OSError("disk unavailable")

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        raise AssertionError("not used")


def test_query_and_persistence_errors_both_retained(harness: Harness) -> None:
    runner = ScriptedRunner([(1, b"", b"failed")])
    with pytest.raises(ExceptionGroup) as caught:
        harness.probe(runner, BrokenStore()).observe(execution(), operation())
    assert isinstance(caught.value.exceptions[0], CommandFailure)
    assert isinstance(caught.value.exceptions[1], OSError)


def test_grouped_transport_failure_retains_partial_evidence(harness: Harness) -> None:
    capture = CommandCapture(
        ("/usr/bin/sacct",), None, b"partial", b"diagnostic", False
    )
    primary = CommandFailure("OUTPUT_LIMIT", capture)
    failure = ExceptionGroup(
        "transport and cleanup", [primary, OSError("close failed")]
    )
    runner = ScriptedRunner([failure])
    with pytest.raises(SchedulerProbeError) as caught:
        harness.probe(runner).observe(execution(), operation())
    assert caught.value.__cause__ is failure
    raw = json.loads(harness.store.read(caught.value.evidence))
    assert len(raw["commands"]) == 1
    assert base64.b64decode(raw["commands"][0]["stdout_base64"]) == b"partial"
    assert raw["commands"][0]["complete"] is False


def test_no_observation_when_successful_queries_cannot_be_saved(
    harness: Harness,
) -> None:
    runner = ScriptedRunner([(0, accounting(), b""), (0, b"", b"")])
    with pytest.raises(OSError):
        harness.probe(runner, BrokenStore()).observe(execution(), operation())


def test_repeated_observation_queries_again_without_mutating_old_evidence(
    harness: Harness,
) -> None:
    runner = ScriptedRunner(
        [
            (0, accounting(state="RUNNING", end="Unknown"), b""),
            (0, b"123|RUNNING\n", b""),
            (0, accounting(), b""),
            (0, b"", b""),
        ]
    )
    probe = harness.probe(runner)
    first = probe.observe(execution(), operation())
    raw = harness.store.read(first.evidence)
    second = probe.observe(execution(), operation())
    assert (
        first.accounting_state == "RUNNING" and second.accounting_state == "COMPLETED"
    )
    assert harness.store.read(first.evidence) == raw and len(runner.calls) == 4


@pytest.mark.parametrize(
    "field,value",
    [
        ("cluster", "--all"),
        ("cluster", "a;b"),
        ("job_id", "1,2"),
        ("job_id", "123.batch"),
        ("job_id", "123_[1-4]"),
        ("job_id", "0"),
        ("raw_job_id", "120_3"),
        ("database_index", ""),
        ("uid", True),
        ("uid", -1),
        ("uid", "1000"),
        ("restart_count", 1.0),
        ("restart_count", None),
        ("submitted_at_epoch", 1700000002),
        ("started_at_epoch", False),
        ("started_at_epoch", 0),
    ],
)
def test_illegal_frozen_identity_before_query(
    harness: Harness, field: str, value: object
) -> None:
    bad = execution().model_copy(update={field: value})
    runner = ScriptedRunner([])
    with pytest.raises(ValidationError):
        harness.probe(runner).observe(bad, operation())
    assert not runner.calls


@pytest.mark.parametrize("value", [None, {}, "", [], 1])
def test_invalid_inputs_rejected(harness: Harness, value: object) -> None:
    runner = ScriptedRunner([])
    with pytest.raises(ValidationError):
        harness.probe(runner).observe(cast(SlurmExecutionIdentity, value), operation())
    assert not runner.calls


def test_real_slurm_probe_completed_check_job(harness: Harness) -> None:
    # Explicit integration fixture, not a permanent dependency on one old job.
    # Ordinary unit regressions may skip this; deployment must run and retain it.
    fixture = os.environ.get("LAB_SLURM_PROBE_FIXTURE")
    if not fixture:
        pytest.skip("real scheduler integration requires an explicitly pinned fixture")
    assert os.environ.get("SLURM_JOB_ID"), "run software checks on compute nodes"
    fixture_bytes = Path(fixture).read_bytes()
    data = json.loads(fixture_bytes)
    item = SlurmExecutionIdentity.model_validate_json(json.dumps(data["execution"]))
    result = harness.probe(SlurmCommandRunner()).observe(item, operation())
    assert (
        result.accounting_state == data["expected_state"] and result.queue_state is None
    )
    assert result.ended_at_epoch == data["expected_end"]
    output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
    assert output
    target = Path(output)
    (target / "slurm-probe-fixture.json").write_bytes(fixture_bytes)
    (target / "slurm-probe-observation.json").write_text(
        result.model_dump_json(indent=2) + "\n"
    )
    (target / "slurm-probe-evidence.json").write_bytes(
        harness.store.read(result.evidence)
    )
