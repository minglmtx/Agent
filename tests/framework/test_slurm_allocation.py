"""Consistent query composition, refusal and original diagnostic preservation."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.slurm.probe import AccountingSlurmProbe
from lab_generate_skill.adapters.slurm.commands import (
    CommandCapture,
    CommandFailure,
    SlurmCommandRunner,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.slurm.kernel_files import KernelRead
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.scheduler import SchedulerProbeError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from allocation_fixtures import Case
from cgroup_fixtures import Control
from test_slurm_probe import NoCancel, operation
from test_linux_cgroups import actual_slurm_execution


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Case:
    return Case(tmp_path, monkeypatch)


def raw_error(case: Case, error: BaseException) -> dict[str, Any]:
    data: object = json.loads(
        case.store.read(getattr(error, "slurm_allocation_evidence_ref"))
    )
    assert isinstance(data, dict)
    return data


def test_normal_repeat_queries_do_not_grant_launch(case: Case) -> None:
    verifier = case.verifier()
    for _ in range(2):
        result = verifier.observe(case.execution, case.writer, operation())
        assert result.facts.execution == case.execution
        assert result.facts.gpu.minor_number == result.facts.controller.gpu_index == 2
        assert result.facts.cgroup == case.membership
        raw = json.loads(case.store.read(result.evidence))
        assert raw["stage"] == "complete" and raw["error_type"] is None
        assert (
            len(raw["commands"])
            == len(raw["kernel_observations"])
            == len(raw["scheduler_observations"])
            == 2
        )
        assert result.evidence.visibility == "private"
    assert case.kernel_calls == case.probe.calls == len(case.runner.calls) == 4
    assert all(
        args[1:] == ("show", "job", "4751471", "--json")
        for args in case.runner.calls[::2]
    )
    assert not hasattr(result, "permit")


@pytest.mark.parametrize(
    "changes",
    [
        {"accounting_state": "COMPLETED"},
        {"queue_state": None},
        {"queue_state": "PENDING"},
        {"exit_status": 1},
        {"exit_signal": 9},
        {"ended_at_epoch": 1793029458},
    ],
)
@pytest.mark.parametrize("after", [0, 1])
def test_nonrunning_accounting_rejected(
    case: Case, changes: dict[str, object], after: int
) -> None:
    case.probe.changes, case.probe.change_after = changes, after
    with pytest.raises(ValueError) as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    raw = raw_error(case, caught.value)
    assert raw["stage"] == ("accounting_after" if after else "accounting_before")
    assert len(case.runner.calls) == (2 if after else 0)


def test_wrong_accounting_incarnation(case: Case) -> None:
    case.probe.changes = {
        "execution": case.execution.model_copy(update={"restart_count": 1})
    }
    with pytest.raises(ValueError) as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    assert raw_error(case, caught.value)["stage"] == "accounting_before"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("controller", b"{}"),
        ("controller", b"\xff"),
        ("gpu", b"<bad/>"),
    ],
)
def test_bad_raw_query_retained(case: Case, field: str, bad: bytes) -> None:
    setattr(case.runner, field, bad)
    with pytest.raises(ValueError) as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    raw = raw_error(case, caught.value)
    assert raw["stage"] == "parse_device_and_controller" and len(raw["commands"]) == 2
    assert case.kernel_calls == case.probe.calls == 1


def test_wrong_physical_device(case: Case) -> None:
    case.runner.gpu = case.runner.gpu.replace(
        b"<minor_number>2</minor_number>", b"<minor_number>3</minor_number>"
    )
    with pytest.raises(ValueError, match="physical GPU") as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    assert len(raw_error(case, caught.value)["commands"]) == 2


def test_kernel_drift_rejected(case: Case) -> None:
    case.drift = True
    with pytest.raises(ValueError, match="containment changed") as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    assert len(raw_error(case, caught.value)["kernel_observations"]) == 2
    assert case.probe.calls == 1


@pytest.mark.parametrize(
    "ending",
    [
        None,
        ProcessTermination(100, "unconfirmed", None, True),
        ProcessTermination(100, "reaped", 1, False),
        ProcessTermination(100, "reaped", 0, True),
        ProcessTermination(100, "reaped", 0, False, ("OSError",)),
    ],
)
def test_command_cleanup_is_required(
    case: Case, ending: ProcessTermination | None
) -> None:
    case.runner.ending = ending
    with pytest.raises(CommandFailure) as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    assert len(raw_error(case, caught.value)["commands"]) == 1
    assert len(case.runner.calls) == 1


def test_partial_query_failure_retained_once(case: Case) -> None:
    capture = CommandCapture(
        ("/usr/bin/scontrol",), None, b"partial", b"diagnostic", False
    )
    case.runner.fail = CommandFailure("QUERY_TIMEOUT", capture)
    with pytest.raises(CommandFailure) as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    raw = raw_error(case, caught.value)
    assert len(raw["commands"]) == 1 and raw["commands"][0]["complete"] is False
    assert caught.value is case.runner.fail


def test_scheduler_failure_reference_preserved(case: Case) -> None:
    case.probe.fail = SchedulerProbeError("BAD_QUEUE", case.probe.reference)
    with pytest.raises(SchedulerProbeError) as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    assert raw_error(case, caught.value)[
        "scheduler_failure"
    ] == case.probe.reference.model_dump(mode="json")


def test_kernel_primary_and_close_errors_preserved(case: Case) -> None:
    primary, cleanup = OSError("read"), OSError("close")
    case.kernel_error = ExceptionGroup("kernel failed", [primary, cleanup])
    setattr(
        case.kernel_error,
        "slurm_kernel_capture",
        KernelCapture((KernelRead("/proc/3910250/status", b"partial", False),), ()),
    )
    with pytest.raises(ExceptionGroup) as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    assert caught.value is case.kernel_error
    assert caught.value.exceptions == (primary, cleanup)
    assert (
        raw_error(case, caught.value)["kernel_observations"][0]["reads"][0]["complete"]
        is False
    )


@pytest.mark.parametrize("query_fails", [False, True])
def test_save_failure_preserves_primary_and_expected_ref(
    case: Case, monkeypatch: pytest.MonkeyPatch, query_fails: bool
) -> None:
    primary, storage = OSError("query failed"), OSError("store failed")
    if query_fails:
        case.runner.fail = primary
    writes = 0

    def fail(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        nonlocal writes
        writes += 1
        raise storage

    monkeypatch.setattr(case.store, "put", fail)
    with pytest.raises((ExceptionGroup, OSError)) as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    if query_fails:
        assert isinstance(caught.value, ExceptionGroup)
        assert caught.value.exceptions == (primary, storage)
    else:
        assert caught.value is storage
    assert isinstance(
        getattr(caught.value, "slurm_allocation_evidence_ref"), EvidenceRef
    )
    assert writes == 1


def test_commit_then_error_keeps_original_complete_bytes(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = case.store.put
    writes = 0

    def commit_fail(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        nonlocal writes
        writes += 1
        original(data, metadata)
        raise OSError("confirmation lost")

    monkeypatch.setattr(case.store, "put", commit_fail)
    with pytest.raises(OSError) as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    assert raw_error(case, caught.value)["stage"] == "complete"
    assert writes == 1 and len(case.runner.calls) == 2


def test_stop_after_save_returns_no_success(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    stopped = False

    class Guard(Control):
        def checkpoint(self) -> float:
            if stopped:
                raise OperationStopped("CANCELLED", "unit")
            return 100

    class Controls:
        def bind(self, op: OperationContext) -> Guard:
            return Guard()

    original = case.store.put

    def save_stop(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        nonlocal stopped
        ref = original(data, metadata)
        stopped = True
        return ref

    monkeypatch.setattr(case.store, "put", save_stop)
    verifier = SlurmAllocationVerifier(
        case.store,
        Controls(),
        case.clock,
        case.probe,
        case.runner,
        scontrol=Path("/usr/bin/scontrol"),
        nvidia_smi=Path("/usr/bin/nvidia-smi"),
    )
    with pytest.raises(OperationStopped) as caught:
        verifier.observe(case.execution, case.writer, operation())
    assert raw_error(case, caught.value)["stage"] == "complete"


def test_binary_paths_checked_before_queries(case: Case) -> None:
    with pytest.raises(ValueError):
        SlurmAllocationVerifier(
            case.store,
            case.controls,
            case.clock,
            case.probe,
            case.runner,
            scontrol=Path("scontrol"),
            nvidia_smi=Path("/usr/bin/nvidia-smi"),
        )
    assert case.runner.calls == [] and case.kernel_calls == 0


@pytest.mark.parametrize("field", ["execution", "writer", "op"])
@pytest.mark.parametrize("bad", [None, "", {}, True])
def test_invalid_inputs_have_no_queries_or_new_evidence(
    case: Case, field: str, bad: Any
) -> None:
    values: dict[str, Any] = dict(
        execution=case.execution, writer=case.writer, op=operation()
    )
    values[field] = bad
    with pytest.raises(ValueError):
        case.verifier().observe(**values)
    assert case.runner.calls == [] and case.kernel_calls == case.probe.calls == 0


def test_wrong_storage_reference_is_rejected(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = case.store.put

    def wrong(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        result = original(data, metadata)
        return result.model_copy(update={"producer": "different"})

    monkeypatch.setattr(case.store, "put", wrong)
    with pytest.raises(ValueError, match="different content identity") as caught:
        case.verifier().observe(case.execution, case.writer, operation())
    assert raw_error(case, caught.value)["stage"] == "complete"


def test_actual_allocation_observer() -> None:
    identity, _ = actual_slurm_execution()
    writer = current_process_identity()
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    root = output / "allocation-evidence"
    root.mkdir(mode=0o700)
    store = FileEvidenceStore(root)
    clock = SystemClock()
    guards = OperationGuards(clock, NoCancel())

    class TrackingRunner(SlurmCommandRunner):
        calls = 0

        def run(
            self, argv: tuple[str, ...], control: OperationControl
        ) -> CommandCapture:
            self.calls += 1
            return super().run(argv, control)

    runner = TrackingRunner()
    probe = AccountingSlurmProbe(
        store,
        guards,
        clock,
        runner,
        sacct=Path("/usr/bin/sacct"),
        squeue=Path("/usr/bin/squeue"),
    )
    verifier = SlurmAllocationVerifier(
        store,
        guards,
        clock,
        probe,
        runner,
        scontrol=Path("/usr/bin/scontrol"),
        nvidia_smi=Path("/usr/bin/nvidia-smi"),
    )
    first = verifier.observe(identity, writer, operation())
    second = verifier.observe(identity, writer, operation())
    assert first.facts.execution == second.facts.execution == identity
    assert first.facts.cgroup == second.facts.cgroup
    assert first.facts.gpu == second.facts.gpu
    assert runner.calls == 12
    for result in (first, second):
        raw = json.loads(store.read(result.evidence))
        assert raw["stage"] == "complete" and raw["error_type"] is None
        assert (
            len(raw["commands"])
            == len(raw["kernel_observations"])
            == len(raw["scheduler_observations"])
            == 2
        )
        assert all(c["termination"]["state"] == "reaped" for c in raw["commands"])
    path = output / "allocation-observation.json"
    with path.open("x") as stream:
        os.chmod(path, 0o600)
        json.dump(
            {
                "schema": "actual-allocation-observer-check/1",
                "first": first.model_dump(mode="json"),
                "second": second.model_dump(mode="json"),
                "query_calls": runner.calls,
                "evidence_root": str(root),
                "production_admission": False,
            },
            stream,
            indent=2,
        )
