"""Invalid input, stop controls and corrupt dependencies never become permission."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.models.generator_resource import registered_generator
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.application.generator_resource_admission import (
    RunGeneratorResourceAuthority,
)
from lab_generate_skill.domain.budget import Money
from lab_generate_skill.domain.errors import (
    EvidenceError,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.generator_model_binding import GeneratorModelBinding
from lab_generate_skill.domain.generator_step import GeneratorStepStarted
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.domain.run_plan import RunPlan, RoleBudget
from lab_generate_skill.domain.run_journal import RunSnapshot
from lab_generate_skill.runtime.lifecycle import OperationGuards
from generator_resource_fixtures import ResourceCase
from generator_resource_admission_fixtures import AdmissionCase, admission_case
from test_generator_resource_admission import a as a, admit
from test_generator_resource import c as c, inspect
from test_run_journal import CancelSwitch
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import installed_sources as installed_sources


@pytest.mark.parametrize("value", [None, {}, [], True])
@pytest.mark.parametrize("field", ["spec", "operation"])
def test_empty_and_wrong_type_rejected(
    a: AdmissionCase, value: Any, field: str
) -> None:
    c = a.resource
    with pytest.raises(ValueError):
        a.authority.authorize_start(
            value if field == "spec" else c.spec,
            value if field == "operation" else c.op,
            c.controls.bind(c.op),
        )
    assert not list(c.journal._root.iterdir()) and not c.authority.workers


@pytest.mark.parametrize("stop", ["cancel", "deadline"])
def test_stopped_control_never_reads_or_authorizes(
    a: AdmissionCase, stop: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = a.resource

    def forbidden(*args: Any) -> None:
        pytest.fail("read after cancellation/deadline")

    monkeypatch.setattr(a.deps.plans, "load", forbidden)
    cancelled = CancelSwitch()
    cancelled.cancelled = True
    changes: dict[str, Any] = {"operation_id": "stopped-resource"}
    if stop == "cancel":
        changes["cancellation_ref"] = CancellationRef(
            channel_id="cancel", run_id="run", owner_id="owner"
        )
    else:
        changes["deadline"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    op = c.op.model_copy(update=changes)
    control = OperationGuards(SystemClock(), cancelled).bind(op)
    with pytest.raises(OperationStopped):
        a.authority.authorize_start(c.spec, op, control)


@pytest.mark.parametrize("which", ["missing_plan", "corrupt_model", "missing_input"])
def test_evidence_failures_before_lower_authority(
    a: AdmissionCase, which: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = a.resource

    def forbidden(*args: Any) -> None:
        pytest.fail("authority after evidence failure")

    monkeypatch.setattr(c.authority, "authorize_start", forbidden)
    ref = (
        a.run.plan_ref
        if which == "missing_plan"
        else (
            c.spec.model_binding_ref
            if which == "corrupt_model"
            else a.plan.task_manifest_ref
        )
    )
    path = c.evidence._blobs / ref.sha256
    if which == "corrupt_model":
        path.write_bytes(b"damaged")
    else:
        path.unlink()
    with pytest.raises(EvidenceError):
        admit(a)
    assert not list(c.journal._root.iterdir())


def test_paid_generator_plan_not_local_resource(
    c: ResourceCase, tmp_path: Path
) -> None:
    def paid(plan: RunPlan) -> RunPlan:
        assert plan.budget is not None
        budget = plan.budget.model_copy(
            update={
                "roles": (
                    RoleBudget(
                        role="generator",
                        budget_id="teacher",
                        reservation_ceiling=Money(units=1),
                    ),
                ),
                "capacity": plan.budget.capacity.model_copy(
                    update={
                        "max_requests": 32,
                        "max_entries": 128,
                        "max_bytes": 2 * 1024 * 1024,
                    }
                ),
            }
        )
        return plan.model_copy(
            update={
                "budget": budget,
                "models": tuple(
                    m.model_copy(update={"paid": m.role == "generator"})
                    for m in plan.models
                ),
            }
        )

    a = admission_case(c, tmp_path / "run-state", change=paid)
    assert next(m for m in a.plan.models if m.role == "generator").paid
    with pytest.raises(OwnershipConflict, match="planned local model"):
        admit(a)


def test_actual_model_payload_foreign_release_rejected(
    c: ResourceCase, tmp_path: Path
) -> None:
    model = GeneratorModelBinding.model_validate_json(
        c.evidence.read(c.spec.model_binding_ref)
    )
    changed = model.model_copy(
        update={
            "release_ref": model.release_ref.model_copy(
                update={"producer": "different-release"}
            )
        }
    )
    ref = c.evidence.put(
        changed.model_dump_json().encode(), local_metadata("model-binding/1")
    )
    c.spec = c.spec.model_copy(update={"model_binding_ref": ref})
    a = admission_case(c, tmp_path / "run-state")
    with pytest.raises(OwnershipConflict, match="Actual Generator model"):
        admit(a)


@pytest.mark.parametrize("which", ["binding", "capacity"])
def test_journal_envelope_mismatch(
    a: AdmissionCase, which: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = a.deps.runs.read(a.resource.op)
    if which == "binding":
        changed = snapshot.model_copy(
            update={
                "binding": snapshot.binding.model_copy(
                    update={
                        "owner": snapshot.binding.owner.model_copy(
                            update={"worker_id": "another"}
                        )
                    }
                )
            }
        )
    else:
        changed = snapshot.model_copy(
            update={
                "capacity": snapshot.capacity.model_copy(
                    update={"max_entries": snapshot.capacity.max_entries + 1}
                )
            }
        )
    changed = RunSnapshot.model_validate(changed)
    monkeypatch.setattr(a.deps.runs, "read", lambda op: changed)
    with pytest.raises(OwnershipConflict, match="journal differs"):
        admit(a)


def test_inconsistent_submission_history_rejected(
    a: AdmissionCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = a.deps.runs.read(a.resource.op)
    changed = snapshot.model_copy(
        update={
            "binding": snapshot.binding.model_copy(update={"submission_key": "another"})
        }
    )
    monkeypatch.setattr(a.deps.runs, "read", lambda op: changed)
    with pytest.raises(
        ValidationError, match="Submission outcome requires matching key"
    ):
        admit(a)


def test_started_requires_original_admission(a: AdmissionCase) -> None:
    c = a.resource
    deps = c.dependencies()
    deps["authority"] = a.authority
    with registered_generator(c.spec, c.op, **deps):
        fact = json.loads(c.evidence.read(inspect(c).events[-1].evidence[0]))
        started = GeneratorStepStarted.model_validate_json(json.dumps(fact["step"]))
        unadmitted = RunGeneratorResourceAuthority(a.run, a.deps)
        with pytest.raises(OwnershipConflict, match="no original resource admission"):
            unadmitted.verify_started(c.spec, started, c.op, c.controls.bind(c.op))
    assert inspect(c).state == "closed"
