"""Explicit policy scope: no implicit enablement, migration, or approval."""

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.optional_policies import (
    EnabledPolicy,
    InactivePolicy,
    RunPolicies,
)
from lab_generate_skill.domain.run_plan import ExecutionWorkload, RunPlan
from test_run_plan import plan, reference


def enabled() -> EnabledPolicy:
    return EnabledPolicy(
        status="enabled",
        reason="selected for this task batch",
        component_id="memory-v1",
        contract_version="1.0",
        configuration_ref=reference("optional-policy-config/1"),
        reviewer_component_id="memory-reviewer-v1",
        reviewer_contract_version="1.0",
        validation_ref=reference("optional-policy-validation/1"),
    )


@pytest.mark.parametrize("status", ["disabled", "not_applicable"])
def test_inactive_policies_are_explicit_and_have_no_extra_inputs(status: str) -> None:
    choice = InactivePolicy.model_validate(dict(status=status, reason="not needed"))
    policies = RunPolicies(actor_memory=choice, teacher_template=choice)
    assert policies.references() == ()
    assert RunPolicies.model_validate_json(policies.model_dump_json()) == policies
    assert policies.references() == ()
    with pytest.raises(ValidationError):
        InactivePolicy.model_validate({**choice.model_dump(), "component_id": "hidden"})


def test_selected_execution_and_review_are_frozen_together() -> None:
    selected = enabled()
    original = plan()
    policies = RunPolicies(actor_memory=selected, teacher_template=selected)
    value = RunPlan.model_validate({**original.model_dump(), "policies": policies})
    assert value.schema_version == "run-plan/3"
    assert policies.references() == (
        selected.configuration_ref,
        selected.validation_ref,
    )
    assert all(ref in value.references() for ref in policies.references())
    assert RunPlan.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        setattr(selected, "component_id", "replacement")


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        "disabled",
        True,
        {"actor_memory": None},
        {
            "actor_memory": {"status": "enabled"},
            "teacher_template": {"status": "disabled", "reason": "x"},
        },
    ],
)
def test_missing_empty_or_wrong_policy_shape_rejected(data: object) -> None:
    with pytest.raises(ValidationError):
        RunPolicies.model_validate(data)


@pytest.mark.parametrize("reason", ["", " \n\t", None, 1, "x" * 2049])
def test_inactive_reason_is_required_and_bounded(reason: object) -> None:
    with pytest.raises(ValidationError):
        InactivePolicy.model_validate(dict(status="disabled", reason=reason))


@pytest.mark.parametrize(
    "change",
    [
        {"contract_version": "1"},
        {"contract_version": True},
        {"reviewer_contract_version": "0.1"},
        {"reviewer_component_id": "memory-v1"},
        {"configuration_ref": reference("other/1")},
        {"validation_ref": reference("optional-policy-validation/1", public=True)},
        {"status": "disabled"},
        {"extra": "ignored"},
    ],
)
def test_selected_policy_cannot_omit_or_mismatch_pins(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        EnabledPolicy.model_validate({**enabled().model_dump(), **change})


@pytest.mark.parametrize("version", ["run-plan/1", "run-plan/2"])
def test_old_plan_version_is_not_given_implicit_policies(version: str) -> None:
    data = plan().model_dump()
    data.pop("policies")
    data["schema_version"] = version
    with pytest.raises(ValidationError):
        RunPlan.model_validate(data)
    data["schema_version"] = "run-plan/3"
    with pytest.raises(ValidationError):
        RunPlan.model_validate(data)


def test_teacher_policy_requires_teacher_but_actor_policy_can_be_selected() -> None:
    original = plan()
    data = original.model_dump()
    data.update(
        purpose="evaluation",
        workload=ExecutionWorkload(
            execution_policy_ref=reference(), task_inputs_ref=reference(), seed=1
        ),
        models=(original.models[0],),
        budget=None,
        run_capacity=JournalCapacity(
            max_attempts=1, max_entries=20, max_bytes=512 * 1024, max_entry_bytes=8192
        ),
        policies=RunPolicies(
            actor_memory=enabled(),
            teacher_template=InactivePolicy(
                status="not_applicable", reason="no Teacher in execution"
            ),
        ),
    )
    assert RunPlan.model_validate(data).request_bounds() == {"actor": 20}
    data["policies"] = RunPolicies(actor_memory=enabled(), teacher_template=enabled())
    with pytest.raises(ValidationError, match="without Teacher"):
        RunPlan.model_validate(data)
