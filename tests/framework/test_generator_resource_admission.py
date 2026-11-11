"""Run-bound resource admission: no launch on rejection, stopped-run cleanup."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor
import pytest

from lab_generate_skill.adapters.models.generator_resource import registered_generator
from lab_generate_skill.application.generator_resource_admission import (
    RunGeneratorResourceAuthority,
)
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.domain.generator_step import GeneratorStepStarted
from lab_generate_skill.domain.generator_step import GeneratorStepCleanup
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.run_plan import RunPlan
from generator_resource_fixtures import ResourceCase
from generator_resource_admission_fixtures import AdmissionCase, admission_case
from test_generator_resource import c as c, inspect
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import installed_sources as installed_sources


@pytest.fixture
def a(c: ResourceCase, tmp_path: Path) -> AdmissionCase:
    return admission_case(c, tmp_path / "run-state")


def admit(a: AdmissionCase) -> None:
    c = a.resource
    a.authority.authorize_start(c.spec, c.op, c.controls.bind(c.op))


def test_normal_repeat_read_only(a: AdmissionCase) -> None:
    before = a.harness.journal.read(a.resource.op)
    admit(a)
    admit(a)
    assert a.harness.journal.read(a.resource.op) == before
    assert not list(a.resource.journal._root.iterdir())


@pytest.mark.parametrize(
    "field", ["owner", "release", "allocation", "recovery", "mode", "parent"]
)
def test_wrong_scope_before_lower_authority(
    a: AdmissionCase, field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = a.resource

    def forbidden(*args: Any) -> None:
        pytest.fail("lower authority called for wrong scope")

    monkeypatch.setattr(c.authority, "authorize_start", forbidden)
    spec, op = c.spec, c.op
    if field == "owner":
        spec = spec.model_copy(
            update={
                "token": spec.token.model_copy(
                    update={
                        "owner": spec.token.owner.model_copy(
                            update={"worker_id": "another"}
                        )
                    }
                )
            }
        )
    elif field == "release":
        spec = spec.model_copy(
            update={
                "release_ref": spec.release_ref.model_copy(update={"sha256": "a" * 64})
            }
        )
    elif field == "allocation":
        op = op.model_copy(update={"allocation_id": "other"})
    elif field == "recovery":
        op = op.model_copy(update={"recovery_ref": None})
    elif field == "mode":
        op = op.cleanup("close", now=datetime.now(timezone.utc), seconds=30)
    else:
        op = op.model_copy(update={"parent_operation_id": "another"})
    with pytest.raises((ValueError, OwnershipConflict)):
        a.authority.authorize_start(spec, op, c.controls.bind(op))


@pytest.mark.parametrize(
    "stage", ["planned", "validated", "claimed", "submitting", "submitted"]
)
def test_not_running(c: ResourceCase, tmp_path: Path, stage: Any) -> None:
    a = admission_case(c, tmp_path / "run-state", stage=stage)
    with pytest.raises(InvalidTransition):
        admit(a)


@pytest.mark.parametrize(
    "field,value",
    [("provider", "other"), ("model", "other/model"), ("model_binding_ref", None)],
)
def test_wrong_planned_model(
    c: ResourceCase, tmp_path: Path, field: str, value: object
) -> None:
    def change(plan: RunPlan) -> RunPlan:
        v = (
            c.spec.model_binding_ref.model_copy(update={"producer": "another"})
            if value is None
            else value
        )
        return plan.model_copy(
            update={
                "models": tuple(
                    m.model_copy(update={field: v}) if m.role == "generator" else m
                    for m in plan.models
                )
            }
        )

    a = admission_case(c, tmp_path / "run-state", change=change)
    with pytest.raises(OwnershipConflict):
        admit(a)


def test_stopped_refuses_before_registration(a: AdmissionCase) -> None:
    a.stop()
    deps = a.resource.dependencies()
    deps["authority"] = a.authority
    with pytest.raises(InvalidTransition):
        with registered_generator(a.resource.spec, a.resource.op, **deps):
            pytest.fail("stopped resource launched")
    assert not list(a.resource.journal._root.iterdir())


def test_lower_error_preserved(
    a: AdmissionCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = OSError("live ownership unavailable")

    def deny(*args: Any) -> None:
        raise error

    monkeypatch.setattr(a.resource.authority, "authorize_start", deny)
    with pytest.raises(OSError) as caught:
        admit(a)
    assert caught.value is error


def test_run_changes_during_admission(
    a: AdmissionCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(a.resource.authority, "authorize_start", lambda *args: a.stop())
    with pytest.raises(RevisionConflict):
        admit(a)


def test_plan_changes_during_admission(
    a: AdmissionCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = a.deps.plans.load
    calls = 0

    def changing(*args: Any) -> RunPlan:
        nonlocal calls
        calls += 1
        plan = original(*args)
        return plan if calls == 1 else plan.model_copy(update={"purpose": "training"})

    monkeypatch.setattr(a.deps.plans, "load", changing)
    with pytest.raises(RevisionConflict):
        admit(a)


def test_foreign_context_and_new_operation_refused(a: AdmissionCase) -> None:
    admit(a)
    with ThreadPoolExecutor(1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(admit, a).result()
    c = a.resource
    op = c.op.model_copy(update={"operation_id": "different"})
    with pytest.raises(OwnershipConflict):
        a.authority.authorize_start(c.spec, op, c.controls.bind(op))


def test_original_cleanup_after_stop_and_lost_plan(a: AdmissionCase) -> None:
    admit(a)
    a.stop()
    c = a.resource
    (c.evidence._blobs / a.run.plan_ref.sha256).unlink()
    op = c.op.cleanup("cleanup", now=datetime.now(timezone.utc), seconds=30)
    a.authority.verify_closed(
        c.spec,
        GeneratorStepCleanup(start_attempted=False),
        ProcessTermination(None, "not_started", None, False, ()),
        op,
        c.controls.bind(op),
    )
    assert len(c.authority.closed) == 1


@pytest.mark.parametrize("kind", ["unadmitted", "wrong_parent", "execute"])
def test_cleanup_requires_original_admission(a: AdmissionCase, kind: str) -> None:
    c = a.resource
    if kind != "unadmitted":
        admit(a)
    op = c.op.cleanup("cleanup", now=datetime.now(timezone.utc), seconds=30)
    if kind == "wrong_parent":
        op = op.model_copy(update={"parent_operation_id": "another"})
    if kind == "execute":
        op = c.op
    with pytest.raises(OwnershipConflict):
        a.authority.verify_closed(
            c.spec,
            GeneratorStepCleanup(start_attempted=False),
            ProcessTermination(None, "not_started", None, False, ()),
            op,
            c.controls.bind(op),
        )
    assert not c.authority.closed


def test_actual_resource_handoff_and_stopped_cleanup(a: AdmissionCase) -> None:
    c = a.resource
    deps = c.dependencies()
    deps["authority"] = a.authority
    with registered_generator(c.spec, c.op, **deps):
        assert inspect(c).state == "acquired"
        a.stop()
        (c.evidence._blobs / a.run.plan_ref.sha256).unlink()
    assert (
        inspect(c).state == "closed"
        and len(c.authority.workers) == len(c.authority.closed) == 1
    )


def test_stop_during_worker_handoff_still_closes_original(
    a: AdmissionCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = a.resource
    original = c.authority.verify_started

    def stopping(*args: Any) -> None:
        original(*args)
        a.stop()

    monkeypatch.setattr(c.authority, "verify_started", stopping)
    deps = c.dependencies()
    deps["authority"] = a.authority
    with pytest.raises(RevisionConflict):
        with registered_generator(c.spec, c.op, **deps):
            pytest.fail("stopped handoff admitted")
    assert inspect(c).state == "closed" and len(c.authority.closed) == 1
