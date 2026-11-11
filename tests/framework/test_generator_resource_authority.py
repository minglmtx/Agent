"""Concrete live resource authority; engineering run scope, no model/API calls."""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import pytest

from lab_generate_skill.adapters.models.generator_resource import registered_generator
from lab_generate_skill.adapters.models import generator_resource_authority as module
from lab_generate_skill.adapters.slurm import cgroup_pin as pin_module
from lab_generate_skill.adapters.slurm.cgroup_quiescence import observe_user_quiescence
from lab_generate_skill.bootstrap.generator_resource import (
    bind_generator_resource_authority,
    GeneratorResourceAuthorities,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    DispatchAlreadyCommitted,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.generator_step import GeneratorStepCleanup
from lab_generate_skill.domain.process_identity import ProcessTermination
from generator_resource_admission_fixtures import AdmissionCase
from test_generator_resource_admission import a as a
from test_generator_resource import c as c, inspect, errors
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import installed_sources as installed_sources


@pytest.fixture
def bound(a: AdmissionCase) -> GeneratorResourceAuthorities:
    c = a.resource
    return bind_generator_resource_authority(
        c.spec,
        c.op,
        run=a.run,
        plans=a.deps.plans,
        runs=a.deps.runs,
        evidence=c.evidence,
        workspace_root=c.workspace_root,
        allocation_verifier=c.allocation_verifier,
    )


def test_actual_run_plan_concrete_authority_and_original_close(
    a: AdmissionCase,
    bound: GeneratorResourceAuthorities,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = []
    original_observe = observe_user_quiescence

    def counted(*args: Any, **kwargs: Any) -> Any:
        reads.append(1)
        return original_observe(*args, **kwargs)

    monkeypatch.setattr(pin_module, "observe_user_quiescence", counted)
    c = a.resource
    deps = c.dependencies()
    deps["authority"] = bound.admission
    with registered_generator(c.spec, c.op, **deps) as engine:
        assert bound.actual.started is not None
        assert bound.actual.started.controller.target.worker.writer == engine.configure(
            c.controls.bind(c.op)
        )
        assert inspect(c).state == "acquired"
    assert bound.actual.closed is not None and inspect(c).state == "closed"
    assert len(bound.actual.observations) == 3
    assert len(reads) == 1
    for ref in bound.actual.observations:
        c.evidence.read(ref)
    original = bound.actual.started
    with pytest.raises(DispatchAlreadyCommitted):
        with registered_generator(c.spec, c.op, **deps):
            pytest.fail("restarted")
    assert bound.actual.started == original
    # Unlike the old engineering fixture, actual authorization made independent
    # kernel/controller/allocation reads. Keep the exact observation references.
    output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
    if output:
        (Path(output) / "generator-resource-authority-observation.json").write_text(
            json.dumps(
                {
                    "job_id": os.environ["SLURM_JOB_ID"],
                    "passed": True,
                    "scope": "engineering",
                    "evidence_root": str(c.evidence._blobs.parent),
                    "started": bound.actual.started.model_dump(mode="json"),
                    "closed": bound.actual.closed.model_dump(mode="json"),
                    "observations": [
                        r.model_dump(mode="json") for r in bound.actual.observations
                    ],
                    "record": inspect(c).model_dump(mode="json"),
                    "lower_fixture_called": bool(
                        c.authority.workers or c.authority.closed
                    ),
                },
                indent=2,
            )
            + "\n"
        )
    assert not c.authority.workers and not c.authority.closed


def test_stop_does_not_prevent_actual_original_close(
    a: AdmissionCase, bound: GeneratorResourceAuthorities
) -> None:
    c = a.resource
    deps = c.dependencies()
    deps["authority"] = bound.admission
    with registered_generator(c.spec, c.op, **deps):
        a.stop()
    assert bound.actual.closed is not None and inspect(c).state == "closed"


@pytest.mark.parametrize("which", ["spec", "operation", "caller", "thread"])
def test_scope_refused_before_verifier(
    a: AdmissionCase,
    bound: GeneratorResourceAuthorities,
    which: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = a.resource

    def forbidden(*args: Any) -> None:
        pytest.fail("verification beyond scope")

    monkeypatch.setattr(c.allocation_verifier, "observe", forbidden)
    spec, op = c.spec, c.op
    if which == "spec":
        spec = spec.model_copy(update={"python_executable": "/another/python"})
    if which == "operation":
        op = op.model_copy(update={"operation_id": "another"})
    if which == "caller":
        monkeypatch.setattr(
            module,
            "current_process_identity",
            lambda: spec.slurm.allocation.facts.writer.model_copy(
                update={"start_ticks": 1}
            ),
        )
    control = c.controls.bind(op)
    with pytest.raises(OwnershipConflict):
        if which == "thread":
            with ThreadPoolExecutor(1) as pool:
                pool.submit(bound.actual.authorize_start, spec, op, control).result()
        else:
            bound.actual.authorize_start(spec, op, control)
    assert not bound.actual.observations


def test_actual_allocation_drift_refused(
    a: AdmissionCase,
    bound: GeneratorResourceAuthorities,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = a.resource
    original = c.spec.slurm.allocation
    changed = original.model_copy(
        update={
            "facts": original.facts.model_copy(
                update={
                    "gpu": original.facts.gpu.model_copy(update={"minor_number": 999})
                }
            )
        }
    )
    monkeypatch.setattr(c.allocation_verifier, "observe", lambda *args: changed)
    with pytest.raises(OwnershipConflict) as caught:
        bound.actual.authorize_start(c.spec, c.op, c.controls.bind(c.op))
    assert getattr(caught.value, "generator_step_evidence_ref") == changed.evidence
    assert not bound.actual.observations


def test_unknown_target_is_never_closed(
    a: AdmissionCase, bound: GeneratorResourceAuthorities
) -> None:
    c = a.resource
    bound.admission.authorize_start(c.spec, c.op, c.controls.bind(c.op))
    op = c.op.cleanup("close", now=datetime.now(timezone.utc), seconds=30)
    with pytest.raises(OwnershipConflict, match="original target"):
        bound.admission.verify_closed(
            c.spec,
            GeneratorStepCleanup(start_attempted=False),
            ProcessTermination(None, "not_started", None, False, ()),
            op,
            c.controls.bind(op),
        )
    assert bound.actual.closed is None


@pytest.mark.parametrize("change", ["name", "worker", "controller", "raw"])
def test_forged_handoff_refused_without_changing_original(
    a: AdmissionCase, bound: GeneratorResourceAuthorities, change: str
) -> None:
    c = a.resource
    deps = c.dependencies()
    deps["authority"] = bound.admission
    with registered_generator(c.spec, c.op, **deps):
        started = bound.actual.started
        assert started is not None
        target = started.controller.target
        if change == "name":
            target = target.model_copy(update={"step_name": "other"})
        if change == "worker":
            target = target.model_copy(
                update={
                    "worker": target.worker.model_copy(
                        update={
                            "writer": target.worker.writer.model_copy(
                                update={"start_ticks": 1}
                            )
                        }
                    )
                }
            )
        changed = started.model_copy(
            update={
                "controller": started.controller.model_copy(update={"target": target})
            }
        )
        if change == "controller":
            changed = started.model_copy(
                update={
                    "controller": started.controller.model_copy(update={"memory": "1M"})
                }
            )
        if change == "raw":
            changed = started.model_copy(
                update={
                    "evidence": c.evidence.put(
                        b"{}",
                        EvidenceMetadata(
                            media_type="application/json",
                            content_schema="generator-step-raw/1",
                            visibility="private",
                            producer="test",
                        ),
                    )
                }
            )
        with pytest.raises((OwnershipConflict, EvidenceIntegrityError)) as caught:
            bound.actual.verify_started(c.spec, changed, c.op, c.controls.bind(c.op))
        if change == "controller":
            ref = getattr(caught.value, "generator_step_evidence_ref")
            raw = json.loads(c.evidence.read(ref))
            assert raw["phase"] == "started" and len(raw["commands"]) == 3
            assert raw["target"] == started.controller.target.model_dump(mode="json")
    assert inspect(c).state == "closed"


def test_actual_observer_failure_keeps_primary_and_quarantine(
    a: AdmissionCase,
    bound: GeneratorResourceAuthorities,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = a.resource
    deps = c.dependencies()
    deps["authority"] = bound.admission
    failure = OSError("independent kernel unavailable")

    def fail(*args: Any) -> Any:
        raise failure

    monkeypatch.setattr(module, "observe_started", fail)
    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **deps):
            pytest.fail("missing actual verification")
    assert list(errors(caught.value))[0] is failure
    assert (
        inspect(c).state == "quarantined"
        and getattr(caught.value, "command_capture").termination.state == "reaped"
    )


def test_close_failure_does_not_hide_body_error(
    a: AdmissionCase,
    bound: GeneratorResourceAuthorities,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = a.resource
    deps = c.dependencies()
    deps["authority"] = bound.admission
    primary = RuntimeError("body")
    cleanup = OSError("independent closure unavailable")

    def fail(*args: Any) -> Any:
        raise cleanup

    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **deps):
            monkeypatch.setattr(module, "observe_closed", fail)
            raise primary
    assert list(errors(caught.value))[:2] == [primary, cleanup]
    assert inspect(c).state == "quarantined" and bound.actual.closed is None


def test_original_removed_tree_closes_with_held_handles(
    a: AdmissionCase,
    bound: GeneratorResourceAuthorities,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synchronize actual removal, then exercise production proof, never fake it."""
    import time
    from lab_generate_skill.domain.slurm_quiescence import SlurmUserRemoval

    c = a.resource
    deps = c.dependencies()
    deps["authority"] = bound.admission
    original_observe = pin_module.PinnedUserTree.observe
    descriptor_numbers: list[int] = []

    def after_kernel_removal(self: pin_module.PinnedUserTree, control: Any) -> Any:
        descriptor_numbers.extend(self._fds)
        until = time.monotonic() + 5
        while time.monotonic() < until:
            control.checkpoint()
            if (
                os.readlink(f"/proc/self/fd/{self._fds[0]}")
                == self.original.user_path + " (deleted)"
            ):
                break
            control.wait(0.01)
        assert os.readlink(f"/proc/self/fd/{self._fds[0]}").endswith(" (deleted)")
        return original_observe(self, control)

    monkeypatch.setattr(pin_module.PinnedUserTree, "observe", after_kernel_removal)
    with registered_generator(c.spec, c.op, **deps):
        assert bound.actual.started is not None
    assert inspect(c).state == "closed" and bound.actual.closed is not None
    assert isinstance(bound.actual.closed.quiescence, SlurmUserRemoval)
    assert bound.actual.closed.schema_version == "generator-step-closed/2"
    raw = json.loads(c.evidence.read(bound.actual.closed.evidence))
    pins = [pin for k in raw["kernel"] for pin in k["pinned_controls"]]
    assert [pin["phase"] for pin in pins] == ["pinned", "removed", "removed"]
    assert pins[1]["events_errno"] == 19 and pins[2]["events_errno"] == 19
    assert 1 <= len(raw["commands"]) <= 10
    assert bound.actual._pin is None
    for fd in descriptor_numbers:
        with pytest.raises(OSError):
            os.fstat(fd)
    output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
    if output:
        (Path(output) / "generator-original-removal.json").write_text(
            json.dumps(
                {"closed": bound.actual.closed.model_dump(mode="json"), "raw": raw},
                indent=2,
            )
            + "\n"
        )


def test_handle_close_failure_preserves_body_and_observation(
    a: AdmissionCase,
    bound: GeneratorResourceAuthorities,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = a.resource
    deps = c.dependencies()
    deps["authority"] = bound.admission
    primary, cleanup = RuntimeError("body"), OSError("close result lost")
    original_close = pin_module.PinnedUserTree.close
    calls = []

    def failed_close(self: pin_module.PinnedUserTree) -> None:
        calls.append(self.original)
        original_close(self)
        raise cleanup

    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **deps):
            monkeypatch.setattr(pin_module.PinnedUserTree, "close", failed_close)
            raise primary
    assert list(errors(caught.value)) == [primary, cleanup]
    assert len(calls) == 1 and bound.actual._pin is None
    record = inspect(c)
    assert record.state == "quarantined"
    ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))
    assert ending["step_closed"] is None
    assert bound.actual.closed is not None  # Diagnostic observation, not a permit.
    assert ending["cleanup_step_evidence"] == [
        bound.actual.closed.evidence.model_dump(mode="json")
    ]
    assert (
        json.loads(c.evidence.read(bound.actual.closed.evidence))["phase"] == "closed"
    )


@pytest.mark.parametrize("where", ["dup", "open"])
def test_pin_acquisition_failure_retains_raw_and_releases_opened_handles(
    a: AdmissionCase,
    bound: GeneratorResourceAuthorities,
    monkeypatch: pytest.MonkeyPatch,
    where: str,
) -> None:
    from types import SimpleNamespace
    from lab_generate_skill.adapters.slurm import cgroup_pin

    c = a.resource
    deps = c.dependencies()
    deps["authority"] = bound.admission
    failure = OSError("pin acquisition failed")
    retained: list[int] = []

    def dup(fd: int) -> int:
        if where == "dup":
            raise failure
        result = os.dup(fd)
        retained.append(result)
        return result

    def open_event(*args: Any, **kwargs: Any) -> int:
        raise failure

    proxy = SimpleNamespace(**vars(os))
    proxy.dup, proxy.open = dup, open_event
    monkeypatch.setattr(cgroup_pin, "os", proxy)
    with pytest.raises(BaseExceptionGroup) as caught:
        with registered_generator(c.spec, c.op, **deps):
            pytest.fail("failed original handle acquisition admitted")
    assert list(errors(caught.value))[0] is failure
    assert bound.actual._pin is None and inspect(c).state == "quarantined"
    assert getattr(caught.value, "command_capture").termination.state == "reaped"
    raw = json.loads(c.evidence.read(getattr(failure, "generator_step_evidence_ref")))
    assert raw["phase"] == "started" and raw["kernel"][0]["controls"]
    for fd in retained:
        with pytest.raises(OSError):
            os.fstat(fd)
