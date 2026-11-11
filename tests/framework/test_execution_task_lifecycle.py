"""Actor-only source on the existing lifecycle; no real source/model qualification."""

from lab_generate_skill.application.execution_task_result import execution_task_result

from pathlib import Path
from lab_generate_skill.ports.lifecycle import OperationControl
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.application.task_execution_evidence import (
    read_original_task_execution,
    TaskExecutionEvidenceDeps,
)
from lab_generate_skill.domain.construction import ConstructionAttemptResult
from lab_generate_skill.domain.actor_admission import (
    ActorAdmissionRequest,
    PreparedActorInput,
)
from lab_generate_skill.domain.actor_inputs import ActorInput
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult
from lab_generate_skill.domain.task_intent import TaskAttemptIntent
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    OperationStopped,
    OwnershipConflict,
)
from execution_task_fixtures import execution_case
from test_run_journal import command


@pytest.mark.parametrize("status", ["success", "failure", "unknown"])
def test_single_source_uses_original_loop_and_full_closed_result(
    tmp_path: Path, status: str
) -> None:
    c = execution_case(tmp_path / "single")
    c.phases.evaluation_status = status
    result = execution_task_result(execute_task(c.plan, c.deps))
    assert isinstance(result, ExecutionTaskResult)
    assert result.evaluation.status == status
    assert (
        result.generations
        == result.interactions
        == c.model.calls
        == c.browser.calls
        == 1
    )
    assert c.source.run.request_bounds() == {"actor": 1}
    assert [r.role for r in c.source.run.models] == ["actor"]
    assert c.source.run.budget is None
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    op = command("single-review")
    original = read_original_task_execution(
        result,
        TaskExecutionEvidenceDeps(
            c.deps.evidence, c.deps.runs, c.deps.states, c.deps.authority
        ),
        op,
        control=c.deps.controls.bind(op),
    )
    assert original.plan == c.plan
    assert original.executed.schema_version == "executed-task-receipt/2"
    assert original.envelope.schema_version == "execution-attempt-result/1"
    assert original.actor.schema_version == "actor-run-request/2"
    assert original.actor.context_configuration_ref == c.source.policy.actor_context_ref
    with pytest.raises(ValidationError):
        ConstructionAttemptResult.model_validate(result.model_dump())
    before = list(c.phases.calls)
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(c.plan, c.deps)
    assert c.phases.calls == before


@pytest.mark.parametrize("gate", ["claim", "resources", "initial"])
def test_original_permissions_remain_mandatory(tmp_path: Path, gate: str) -> None:
    c = execution_case(tmp_path / "single")
    if gate == "claim":
        c.source.claim_authority.denied = True
    if gate == "resources":
        c.authority.denied = True
    if gate == "initial":
        c.authority.initial_denied = True
    with pytest.raises((PermissionError, OwnershipConflict, TaskExecutionUnconfirmed)):
        execute_task(c.plan, c.deps)
    assert c.model.calls == c.browser.calls == 0
    if gate == "initial":
        assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    else:
        assert not c.phases.calls


@pytest.mark.parametrize("phase", ["prepare", "start", "model"])
def test_cancel_or_partial_failure_keeps_original_attempt_and_closes(
    tmp_path: Path, phase: str
) -> None:
    c = execution_case(tmp_path / "single")
    c.phases.errors[phase] = OperationStopped(
        "CANCELLED", "unit original operation stopped"
    )
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    assert caught.value.plan == c.plan
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
    before = list(c.phases.calls)
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(c.plan, c.deps)
    assert c.phases.calls == before


def test_initial_actor_policy_mismatch_refuses_before_model(tmp_path: Path) -> None:
    c = execution_case(tmp_path / "single")
    c.phases.initialized = c.phases.initialized.model_copy(
        update={
            "actor": c.phases.initialized.actor.model_copy(
                update={"candidate_id": "different"}
            )
        }
    )
    with pytest.raises(TaskExecutionUnconfirmed):
        execute_task(c.plan, c.deps)
    assert c.model.calls == c.browser.calls == 0
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"schema_version": "execution-task-intent/1"},
        {"candidate_slot": 0},
        {"execution_policy_ref": None},
        {"execution_inputs_ref": "wrong"},
        {"execution_inputs_ref": None},
    ],
)
def test_execution_intent_requires_exact_policy_inputs_and_no_candidate_slot(
    tmp_path: Path, change: dict[str, object]
) -> None:
    c = execution_case(tmp_path / "single")
    value = c.plan.intent.model_dump()
    if not change:
        value = {}
    elif change == {"schema_version": "execution-task-intent/1"}:
        value["schema_version"] = "construction-attempt-intent/1"
    else:
        value.update(change)
    with pytest.raises(ValidationError):
        TaskAttemptIntent.model_validate(value)


@pytest.mark.parametrize("value", [None, [], 0, "wrong", {}])
def test_wrong_or_empty_plan_refused_without_effect(
    tmp_path: Path, value: object
) -> None:
    c = execution_case(tmp_path / "single")
    with pytest.raises(ValidationError):
        TaskExecutionPlan.model_validate(value)
    assert not c.phases.calls


def test_execution_versions_roundtrip_and_cannot_enter_candidate_admission(
    tmp_path: Path,
) -> None:
    c = execution_case(tmp_path / "single")
    assert TaskExecutionPlan.model_validate_json(c.plan.model_dump_json()) == c.plan
    assert "candidate_slot" not in c.plan.intent.model_dump()
    assert "execution_policy_ref" in c.plan.intent.model_dump()
    with pytest.raises(ValidationError):
        TaskExecutionPlan.model_validate(
            {**c.plan.model_dump(), "schema_version": "task-execution-plan/1"}
        )
    with pytest.raises(ValidationError):
        ActorAdmissionRequest(
            intent=c.plan.intent,
            equivalence_ref=c.phases.initialized.equivalence_ref,
            skill_ref=c.plan.skill_ref,
            operation=c.plan.operation,
            read_operation=c.plan.read_operation,
        )
    snapshot = c.deps.runs.read(c.plan.read_operation)
    state = c.deps.source.open(c.plan, snapshot, c.deps.controls.bind(c.plan.operation))
    assert state.source_kind == "execution"
    # A construction revision may never be fabricated for this source mode.
    with pytest.raises(ValidationError):
        PreparedActorInput(
            schema_version="prepared-actor-input/2",
            binding=c.plan.intent.binding,
            operation=c.plan.operation,
            equivalence_ref=c.phases.initialized.equivalence_ref,
            baseline_ref=c.phases.initialized.baseline_ref,
            run_revision=0,
            construction_revision=0,
            execution_source_ref=c.plan.source_ref,
            actor_input=ActorInput(
                source_context_id=c.source.inputs.source.scope.context_id,
                task=c.source.inputs.candidate_inputs.public_task,
                skill=c.source.policy.skill,
                initial_observation=ResolvedObservation(
                    record=c.source.inputs.candidate_inputs.observation,
                    text=c.source.inputs.candidate_inputs.observation.text,
                ),
            ),
        )


@pytest.mark.parametrize(
    "phase", ["prepare", "model", "capture", "close", "verify_closed", "restore"]
)
def test_partial_or_cleanup_failure_preserves_original_error_without_replay(
    tmp_path: Path, phase: str
) -> None:
    c = execution_case(tmp_path / "single")
    original = OSError("original unit " + phase + " partial failure")
    c.phases.errors[phase] = original
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    error = caught.value
    if phase == "model":
        assert getattr(error.primary, "primary", None) is not None
    elif phase in ("close", "verify_closed", "restore"):
        assert original in error.cleanup_errors
    else:
        assert error.primary is original
    if phase in ("close", "verify_closed"):
        assert "restore" not in c.phases.calls
    before = list(c.phases.calls)
    with pytest.raises(DispatchAlreadyCommitted):
        execute_task(c.plan, c.deps)
    assert c.phases.calls == before


def test_revocation_after_prepare_blocks_actor_and_keeps_owned_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = execution_case(tmp_path / "single")
    hit = c.phases.hit

    def revoke(name: str, control: OperationControl) -> None:
        hit(name, control)
        if name == "prepare":
            c.source.claim_authority.denied = True

    monkeypatch.setattr(c.phases, "hit", revoke)
    with pytest.raises(TaskExecutionUnconfirmed) as caught:
        execute_task(c.plan, c.deps)
    assert isinstance(caught.value.primary, OwnershipConflict)
    assert c.model.calls == c.browser.calls == 0
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]
