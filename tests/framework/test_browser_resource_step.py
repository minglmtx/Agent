"""CPU resource boundaries and original step failures, using explicit unit facts."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym import step as runtime
from lab_generate_skill.adapters.browsergym.step import (
    observe_started as actual_started,
    observe_closed as actual_closed,
)
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.adapters.slurm.linux_cgroups import KernelCgroupObservation
from lab_generate_skill.adapters.slurm.cgroup_quiescence import (
    KernelQuiescenceObservation,
)
from lab_generate_skill.adapters.slurm.step import (
    SlurmStepObservation,
    SlurmStepObserver,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.slurm_step import SlurmControllerStep
from lab_generate_skill.domain.slurm_quiescence import SlurmUserQuiescence
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.ports.lifecycle import OperationControl
from browser_resource_fixtures import resource_case, ResourceCase
from browser_step_fixtures import UnitProcesses
from generator_worker_fixtures import unit_guard
from test_browser_resource import enter, inspect


@pytest.fixture
def c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ResourceCase:
    return resource_case(tmp_path, monkeypatch)


@pytest.mark.parametrize(
    "kind",
    [
        "legacy",
        "missing",
        "wrong_job",
        "worker_parent",
        "wrong_uid",
        "relative",
        "traversal",
        "empty",
        "wrong_type",
    ],
)
def test_slurm_spec_rejects_ambiguous_inputs(c: ResourceCase, kind: str) -> None:
    data = c.spec.model_dump()
    if kind == "legacy":
        data["schema_version"] = "browser-resource-spec/1"
    elif kind == "missing":
        del data["slurm"]
    elif kind == "wrong_job":
        data["slurm"]["execution"]["job_id"] = "123"
    elif kind == "worker_parent":
        data["slurm"]["parent"]["step_id"] = "0"
    elif kind == "wrong_uid":
        data["slurm"]["parent"]["uid"] += 1
    else:
        data["slurm"]["srun_executable"] = {
            "relative": "srun",
            "traversal": "/bin/../srun",
            "empty": "",
            "wrong_type": None,
        }[kind]
    with pytest.raises(ValueError):
        BrowserResourceSpec.model_validate(data)
    assert not c.channels and not list(c.journal._root.iterdir())


class UnitPin:
    def __init__(self, original: Any, parent: Any) -> None:
        self.original, self.parent = original, parent
        self.opened = KernelCapture((), ())
        self.failure: BaseException | None = None
        self.closed = False

    def observe(self, control: OperationControl) -> KernelQuiescenceObservation:
        control.checkpoint()
        if self.failure:
            raise self.failure
        return KernelQuiescenceObservation(
            SlurmUserQuiescence(
                original=self.original, observer=self.parent, writer_status="missing"
            ),
            self.opened,
        )

    def close(self) -> None:
        self.closed = True


def setup_observer(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, kind: str = "normal"
) -> tuple[runtime.BrowserStepState, Any, list[UnitPin]]:
    guard = unit_guard(c.spec.slurm.parent.writer, c.controls.bind(c.op))
    launcher = guard.controller.model_copy(
        update={"process_id": guard.controller.process_id + 10000002}
    )
    state = runtime.BrowserStepState(launcher=launcher)
    parent = c.spec.slurm.parent
    member = parent.model_copy(
        update={
            "step_id": "0",
            "writer": guard.worker,
            "user_inode": parent.user_inode + 100,
            "task_inode": parent.task_inode + 100,
            "user_path": parent.user_path.replace("step_batch", "step_0"),
        }
    )
    reads = 0
    pins: list[UnitPin] = []

    def observe(
        execution: Any, writer: Any, control: OperationControl
    ) -> KernelCgroupObservation:
        nonlocal reads
        reads += 1
        value = (
            parent.model_copy(update={"writer": writer})
            if writer == launcher
            else member.model_copy(update={"writer": writer})
        )
        if (
            (kind == "launcher" and writer == launcher)
            or (kind == "supervisor" and writer == guard.supervisor)
            or (kind == "drift" and reads == 4)
        ):
            value = value.model_copy(update={"user_inode": value.user_inode + 1})
        return KernelCgroupObservation(value, KernelCapture((), ()))

    def pin(original: Any, control: OperationControl) -> Any:
        if kind == "pin":
            raise OSError("pin unavailable")
        value = UnitPin(original, parent.writer)
        pins.append(value)
        return value

    def controller(
        self: Any,
        target: Any,
        control: OperationControl,
        *,
        require_absent: bool = False,
    ) -> SlurmStepObservation:
        if kind == "controller":
            raise OSError("controller failed")
        value = (
            None
            if require_absent
            else SlurmControllerStep(
                target=target,
                started_at_epoch=target.execution.started_at_epoch,
                gpu_type=None,
                memory="1M",
            )
        )
        return SlurmStepObservation(target, value, ())

    def absent(
        self: Any, expected: Any, control: OperationControl
    ) -> SlurmStepObservation:
        return SlurmStepObservation(expected.target, None, ())

    monkeypatch.setattr(runtime, "observe_process_cgroup", observe)
    monkeypatch.setattr(runtime, "pin_user_tree", pin)
    monkeypatch.setattr(
        runtime,
        "pin_browser_processes",
        lambda guard, target, control: UnitProcesses(guard, target),
    )
    monkeypatch.setattr(SlurmStepObserver, "observe", controller)
    monkeypatch.setattr(SlurmStepObserver, "wait_absent", absent)
    return state, guard, pins


def test_original_target_roundtrip_and_close(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, guard, pins = setup_observer(c, monkeypatch)
    control = c.controls.bind(c.op)
    started = actual_started(c.spec, state, guard, c.evidence, control)
    assert state.target is not None and started.controller.target == state.target
    assert json.loads(c.evidence.read(started.evidence))["phase"] == "started"
    ending = ProcessTermination(state.target.launcher.process_id, "reaped", 0, False)
    closed = actual_closed(c.spec, state, ending, c.evidence, control)
    assert closed is not None and closed.target == state.target
    assert json.loads(c.evidence.read(closed.evidence))["phase"] == "closed"
    pins[0].close()


@pytest.mark.parametrize(
    "kind", ["launcher", "supervisor", "drift", "pin", "controller"]
)
def test_failed_acquisition_retains_partial_facts(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    state, guard, pins = setup_observer(c, monkeypatch, kind)
    with pytest.raises(Exception) as caught:
        actual_started(c.spec, state, guard, c.evidence, c.controls.bind(c.op))
    ref = getattr(caught.value, "browser_step_evidence_ref")
    raw = json.loads(c.evidence.read(ref))
    assert raw["phase"] == "started" and raw["error"] is not None
    assert state.started is None
    assert (state.target is None) == (kind in ("launcher", "supervisor"))
    for pin in pins:
        pin.close()


@pytest.mark.parametrize("kind", ["target", "termination", "foreign_pid", "quiescence"])
def test_unconfirmed_close_never_becomes_empty_clean_tree(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    state, guard, pins = setup_observer(c, monkeypatch)
    control = c.controls.bind(c.op)
    actual_started(c.spec, state, guard, c.evidence, control)
    assert state.launcher is not None
    ending = ProcessTermination(state.launcher.process_id, "reaped", 0, False)
    if kind == "target":
        state.target = None
    elif kind == "termination":
        ending = ProcessTermination(
            state.launcher.process_id, "unconfirmed", None, True
        )
    elif kind == "foreign_pid":
        ending = ProcessTermination(state.launcher.process_id + 1, "reaped", 0, False)
    else:
        pins[0].failure = FileNotFoundError(
            "original cgroup missing without held proof"
        )
    with pytest.raises(Exception) as caught:
        actual_closed(c.spec, state, ending, c.evidence, control)
    assert (
        json.loads(c.evidence.read(getattr(caught.value, "browser_step_evidence_ref")))[
            "error"
        ]
        is not None
    )
    pins[0].close()


@pytest.mark.parametrize("kind", ["step_proof", "pin_close"])
def test_resource_step_cleanup_failure_quarantines_and_releases_handles(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    holder: list[UnitPin] = []
    original = runtime.observe_started

    def started(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        state = args[1]
        pin = UnitPin(state.target.worker, c.spec.slurm.parent.writer)
        holder.append(pin)
        if kind == "pin_close":

            def close() -> None:
                pin.closed = True
                raise OSError("pin close failed")

            monkeypatch.setattr(pin, "close", close)
        state.pin = pin
        return result

    monkeypatch.setattr(runtime, "observe_started", started)
    if kind == "step_proof":

        def failed(*args: Any, **kwargs: Any) -> Any:
            raise OSError("step closure unconfirmed")

        monkeypatch.setattr(runtime, "observe_closed", failed)
    with pytest.raises(BaseExceptionGroup):
        with enter(c):
            pass
    assert inspect(c).state == "quarantined" and holder[0].closed
    assert (
        c.channels[0].capture.termination is not None
        and c.channels[0].capture.termination.state == "reaped"
    )


def test_repeat_observation_cannot_replace_live_pinned_target(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, guard, pins = setup_observer(c, monkeypatch)
    control = c.controls.bind(c.op)
    first = actual_started(c.spec, state, guard, c.evidence, control)
    with pytest.raises(Exception, match="already observed"):
        actual_started(c.spec, state, guard, c.evidence, control)
    assert state.started == first and len(pins) == 1 and id(state.pin) == id(pins[0])
    pins[0].close()


@pytest.mark.parametrize("mode", ["lost_ack", "all_raw_fail"])
def test_raw_step_publication_failure_keeps_candidate_refs_and_closes(
    c: ResourceCase,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef

    _, _, pins = setup_observer(c, monkeypatch)
    monkeypatch.setattr(runtime, "observe_started", actual_started)
    monkeypatch.setattr(runtime, "observe_closed", actual_closed)
    original = c.evidence.put
    primary = OSError("step raw publication failed")
    count = 0

    def put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        nonlocal count
        if metadata.content_schema == "browser-step-raw/1":
            count += 1
            if mode == "all_raw_fail":
                raise OSError("all raw unavailable")
            if count == 1:
                original(data, metadata, control=control)
                raise primary
        return original(data, metadata, control=control)

    monkeypatch.setattr(c.evidence, "put", put)
    with pytest.raises((OSError, BaseExceptionGroup)) as caught:
        with enter(c):
            pytest.fail("raw publication failed")
    record = inspect(c)
    ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))
    candidates = ending["details"]["step_diagnostic_candidates"]
    assert candidates and all(
        r["content_schema"] == "browser-step-raw/1" for r in candidates
    )
    assert c.channels[0].capture.termination is not None
    assert c.channels[0].capture.termination.state == "reaped" and pins[0].closed
    if mode == "lost_ack":
        assert caught.value is primary and record.state == "closed"
        assert candidates[0] == getattr(
            primary, "browser_step_evidence_ref"
        ).model_dump(mode="json")
        assert (
            json.loads(c.evidence.read(EvidenceRef.model_validate(candidates[0])))[
                "phase"
            ]
            == "started"
        )
    else:
        assert (
            isinstance(caught.value, BaseExceptionGroup)
            and record.state == "quarantined"
        )
        # All three independently attempted facts retain their candidate
        # addresses: original start, original closure and private raw capture.
        assert len(candidates) == 3
        assert len({ref["sha256"] for ref in candidates}) == 3


@pytest.mark.parametrize("failure_stage", ["process_stop", "process_close"])
def test_process_handle_failure_still_observes_and_closes_original_tree(
    c: ResourceCase,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    original = runtime.observe_started
    handles: list[UnitProcesses] = []
    pins: list[UnitPin] = []
    failure = OSError(failure_stage)

    def started(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        state = args[1]
        pin = UnitPin(state.target.worker, c.spec.slurm.parent.writer)
        process = UnitProcesses(args[2], state.target)
        pins.append(pin)
        handles.append(process)
        if failure_stage == "process_stop":

            def stop(control: OperationControl) -> Any:
                raise failure

            monkeypatch.setattr(process, "stop", stop)
        else:

            def close() -> None:
                process.closed = True
                raise failure

            monkeypatch.setattr(process, "close", close)
        state.pin, state.processes = pin, process
        return result

    monkeypatch.setattr(runtime, "observe_started", started)
    with pytest.raises(BaseExceptionGroup) as caught:
        with enter(c):
            pass
    assert failure in caught.value.exceptions
    assert pins[0].closed and handles[0].closed and inspect(c).state == "quarantined"
    ending = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))["details"]
    assert ending["process_stop"] is not None and ending["step_closed"] is not None
    assert ending["termination"]["state"] == "reaped"
