"""New resource seam: schema cutover, once-only start, and failed evidence/closure."""

import json
import base64
from typing import Any
from pathlib import Path
import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.models.generator_resource import registered_generator
from lab_generate_skill.adapters.models import generator_step as step_module
from lab_generate_skill.adapters.slurm import cgroup_pin as pin_module
from lab_generate_skill.adapters.slurm.step import SlurmStepObserver
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.generator_step import (
    GeneratorStepClosed,
    GeneratorStepStarted,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.slurm_allocation import SlurmAllocationObservation
from lab_generate_skill.ports.lifecycle import OperationControl
from generator_resource_fixtures import ResourceCase
from test_generator_resource import c as c, inspect, errors
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import installed_sources as installed_sources


@pytest.mark.parametrize(
    "which",
    [
        "old_schema",
        "old_provider",
        "missing_slurm",
        "old_cuda",
        "wrong_job",
        "bad_srun",
        "empty_control",
        "not_batch",
    ],
)
def test_spec_cutover_rejects_old_or_ambiguous_binding(
    c: ResourceCase, which: str
) -> None:
    value = c.spec.model_dump()
    if which == "old_schema":
        value["schema_version"] = "generator-resource-spec/2"
    elif which == "old_provider":
        value["token"]["provider_version"] = "1"
    elif which == "missing_slurm":
        del value["slurm"]
    elif which == "old_cuda":
        value["cuda_visible_devices"] = "0"
    elif which == "wrong_job":
        value["token"]["owner"]["job_id"] = "other"
    elif which == "bad_srun":
        value["slurm"]["srun_executable"] = "/bin/../srun"
    elif which == "empty_control":
        value["slurm"]["scontrol_executable"] = ""
    else:
        cg = value["slurm"]["allocation"]["facts"]["cgroup"]
        cg["step_id"] = "0"
        cg["user_path"] = cg["user_path"].replace("step_batch", "step_0")
    with pytest.raises(ValueError):
        GeneratorResourceSpec.model_validate(value)
    assert not list(c.journal._root.iterdir())


def test_allocation_drift_rejects_before_resource_events(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = c.spec.slurm.allocation
    changed = original.model_copy(
        update={
            "facts": original.facts.model_copy(
                update={
                    "gpu": original.facts.gpu.model_copy(
                        update={"uuid": "GPU-00000000-0000-0000-0000-000000000001"}
                    )
                }
            )
        }
    )

    def drift(*args: Any, **kwargs: Any) -> SlurmAllocationObservation:
        return changed

    monkeypatch.setattr(c.allocation_verifier, "observe", drift)
    with pytest.raises(OwnershipConflict, match="allocation changed"):
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pytest.fail("drift admitted")
    assert not list(c.journal._root.iterdir()) and not c.authority.workers


@pytest.mark.parametrize("when", ["before", "after"])
def test_unknown_start_keeps_quarantine(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    start = FramedProcessSession.start
    failure = OSError("start result unknown")
    calls = 0

    def uncertain(self: FramedProcessSession, control: OperationControl) -> None:
        nonlocal calls
        calls += 1
        if when == "after":
            start(self, control)
        raise failure

    monkeypatch.setattr(FramedProcessSession, "start", uncertain)
    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pytest.fail("unknown accepted")
    assert list(errors(caught.value))[0] is failure and calls == 1
    assert inspect(c).state == "quarantined" and not c.authority.closed
    ending = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))
    assert ending["start_attempted"] is True and ending["target"] is None
    assert ending["primary_step_evidence"] is not None
    assert ending["termination"]["state"] == (
        "not_started" if when == "before" else "reaped"
    )


@pytest.mark.parametrize("when", ["start_lost_ack", "all_raw_fail"])
def test_raw_publication_failure_preserves_original_and_closes(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    put = c.evidence.put
    count = 0
    failure = OSError("step raw commit lost")

    def failing(
        payload: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
    ) -> EvidenceRef:
        nonlocal count
        if metadata.content_schema == "generator-step-raw/1":
            count += 1
            if when == "all_raw_fail":
                raise failure
            if count == 1:
                put(payload, metadata)
                raise failure
        return put(payload, metadata)

    monkeypatch.setattr(c.evidence, "put", failing)
    with pytest.raises((OSError, BaseExceptionGroup)) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pytest.fail("failed evidence admitted")
    assert failure in list(errors(caught.value))
    assert getattr(caught.value, "command_capture").termination.state == "reaped"
    assert inspect(c).state == ("closed" if when == "start_lost_ack" else "quarantined")
    expected = getattr(failure, "generator_step_evidence_ref")
    if when == "start_lost_ack":
        # The original successful publication is retained; no start replay.
        assert json.loads(c.evidence.read(expected))["phase"] == "started"
        assert count == 2
    assert not c.authority.workers


def test_controller_failure_preserves_target_for_physical_close(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    observe = SlurmStepObserver.observe
    failure = OSError("controller read failed")

    def fail_live(self: SlurmStepObserver, *args: Any, **kwargs: Any) -> Any:
        if not kwargs.get("require_absent", False):
            raise failure
        return observe(self, *args, **kwargs)

    monkeypatch.setattr(SlurmStepObserver, "observe", fail_live)
    with pytest.raises((OSError, BaseExceptionGroup)) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pytest.fail("controller failure accepted")
    leaves = list(errors(caught.value))
    assert leaves[0] is failure
    record = inspect(c)
    fact = json.loads(c.evidence.read(record.events[-1].evidence[0]))
    assert fact["target"] is not None and fact["step_started"] is None
    assert fact["primary_step_evidence"] is not None
    assert fact["termination"]["state"] == "reaped"
    if len(leaves) == 1:
        assert caught.value is failure and record.state == "closed"
        assert fact["step_closed"] is not None
    else:
        # srun reaping does not imply controller propagation. Only this exact
        # observed stale original step is an allowed additional failure here.
        assert len(leaves) == 2 and isinstance(leaves[1], ValueError)
        assert (
            str(leaves[1]) == "Controller did not return the explicit empty-step result"
        )
        assert record.state == "quarantined" and fact["step_closed"] is None
        raw = json.loads(
            c.evidence.read(getattr(leaves[1], "generator_step_evidence_ref"))
        )
        assert raw["phase"] == "closed" and raw["target"] == fact["target"]
        assert len(raw["commands"]) == 1
        response = json.loads(base64.b64decode(raw["commands"][0]["stdout_base64"]))
        assert len(response["steps"]) == 1
        assert response["steps"][0]["id"] == (
            fact["target"]["execution"]["job_id"]
            + "."
            + fact["target"]["worker"]["step_id"]
        )
        assert response["steps"][0]["state"] == ["RUNNING"]


def test_quiescence_failure_never_releases_resource(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = OSError("original cgroup unavailable")
    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):

            def unavailable(*args: Any, **kwargs: Any) -> Any:
                raise failure

            from lab_generate_skill.adapters.slurm import gpu_step_observation

            monkeypatch.setattr(
                gpu_step_observation, "observe_user_quiescence", unavailable
            )
            monkeypatch.setattr(pin_module, "observe_user_quiescence", unavailable)
    assert failure in list(errors(caught.value)) and inspect(c).state == "quarantined"
    assert getattr(caught.value, "command_capture").termination.state == "reaped"
    assert not c.authority.closed


def test_acquired_and_closed_facts_bind_original_step(c: ResourceCase) -> None:
    with registered_generator(c.spec, c.op, **c.dependencies()) as engine:
        raw = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))
        started = GeneratorStepStarted.model_validate_json(json.dumps(raw["step"]))
        assert (
            started.controller.target.launcher.process_id
            != started.controller.target.worker.writer.process_id
        )
        assert started.controller.target.worker.writer == engine.configure(
            c.controls.bind(c.op)
        )
        assert json.loads(c.evidence.read(started.evidence))["phase"] == "started"
    ending = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))
    closed = GeneratorStepClosed.model_validate_json(json.dumps(ending["step_closed"]))
    assert closed.target == started.controller.target
    assert ending["termination"]["process_id"] == closed.target.launcher.process_id
    assert json.loads(c.evidence.read(closed.evidence))["phase"] == "closed"
    assert ending["primary_step_evidence"] is None and ending["cleanup_errors"] == []


@pytest.mark.parametrize("change", ["missing", "foreign", "empty", "type", "schema"])
def test_invalid_authority_closure_cannot_close_resource(
    c: ResourceCase, change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = c.authority.verify_closed

    def invalid(*args: Any, **kwargs: Any) -> Any:
        closed = original(*args, **kwargs)
        assert closed is not None
        if change == "missing":
            return None
        if change == "empty":
            return {}
        if change == "type":
            return "closed"
        if change == "schema":
            return closed.model_copy(update={"schema_version": "old"})
        return closed.model_copy(
            update={"target": closed.target.model_copy(update={"step_name": "another"})}
        )

    monkeypatch.setattr(c.authority, "verify_closed", invalid)
    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **c.dependencies()):
            pass
    expected = (
        OwnershipConflict if change in ("missing", "foreign") else ValidationError
    )
    leaves = list(errors(caught.value))
    assert len(leaves) == 1 and isinstance(leaves[0], expected)
    record = inspect(c)
    assert record.state == "quarantined"
    ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))
    assert ending["step_closed"] is None
    assert getattr(caught.value, "command_capture").termination.state == "reaped"
