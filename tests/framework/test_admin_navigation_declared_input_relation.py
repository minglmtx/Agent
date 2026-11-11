"""Actual declared-preparation/native-codec seam; no model/site effects."""

from typing import Any

import pytest
from pydantic import ValidationError
from test_admin_navigation_input import contracts as contracts
from test_native_execution_input import recipe as recipe
from admin_production_task_plan import prepare_admin_execution_configuration
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.sites.shopping_admin.tasks.navigation_native_request import (
    NavigationNativeRequestChecks,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)


@pytest.fixture
def native_case(recipe: Any) -> Any:
    c, kwargs = recipe
    prepared = prepare_admin_execution_configuration(**kwargs)
    original = c.owned.bundle.preparation
    # A fresh declaration-only original producer keeps the already-bound owned
    # lifecycle frozen. This seam never calls acquire, prepare or authority.
    plan = TaskExecutionPlan.model_validate_json(
        original.plan.model_copy(
            update={
                "reset_plan_ref": prepared.reset_ref,
                "declaration_ref": prepared.preparation_ref,
                "evaluation": prepared.evaluation,
                "operation": prepared.operation,
                "read_operation": prepared.read_operation,
                "cleanup_seconds": prepared.cleanup_seconds,
            }
        ).model_dump_json()
    )
    from lab_generate_skill.adapters.sites.task_preparation import (
        RecordedSiteTaskPreparation,
    )
    from lab_generate_skill.adapters.sites.task_preparation_state import (
        TaskPreparationState,
    )

    prep = RecordedSiteTaskPreparation(
        plan,
        prepared.preparation,
        original.spec,
        original.site,
        original.resources,
        c.source.site.evidence,
        original.controls,
        original.authority,
        original.qualifications,
        original.records,
        TaskPreparationState(),
    )
    store = c.source.site.evidence
    spec, reset, binding = prep._declared(guard(30))
    declaration = prep.declaration
    raw = store.read(declaration.private_input_ref)
    wrapped = NavigationExecutionInput.model_validate_json(raw)
    assert raw == wrapped.model_dump_json().encode()
    assert declaration.private_input_ref != binding.private_spec_ref
    assert wrapped.spec.model_dump_json().encode() == store.read(
        binding.private_spec_ref
    )
    request = SiteTaskRequest(
        task=declaration.scope.task,
        binding_ref=declaration.task_binding_ref,
        operation=declaration.snapshot_operation,
        action="snapshot",
        private_input=raw.decode(),
    )
    recovery = RecoveryPlan.model_validate_json(store.read(reset.task_recovery_ref))
    environment = RecoveryPlan.model_validate_json(
        store.read(reset.environment_recovery_ref)
    )
    return c, prep, spec, binding, request, recovery, environment


def check(value: Any, *, request: Any = None, binding: Any = None) -> None:
    _, _, spec, original_binding, original_request, recovery, environment = value
    NavigationNativeRequestChecks().verify_inputs(
        spec.configuration,
        original_request if request is None else request,
        original_binding if binding is None else binding,
        recovery,
        environment,
        None,
        None,
        guard(30),
    )


def test_same_native_envelope_passes_declared_and_native_guards_without_effects(
    native_case: Any,
) -> None:
    c, prep, spec, binding, _, _, _ = native_case
    for _ in range(2):
        assert prep._declared(guard(30))[::2] == (spec, binding)
        check(native_case)
    assert prep.state.phase == "new"
    assert c.owned.resources.site.phase == "new"
    assert c.owned.resources.browser() is None


@pytest.mark.parametrize("bad", ["", "{}", "[]", "null", "false", "1"])
def test_empty_or_wrong_native_body_still_rejected(native_case: Any, bad: str) -> None:
    request = native_case[4].model_copy(update={"private_input": bad})
    with pytest.raises((ValidationError, OwnershipConflict)):
        check(native_case, request=request)
    assert native_case[1].state.phase == "new"


def test_wrong_binding_spec_and_unwrapped_input_still_rejected(
    native_case: Any,
) -> None:
    _, prep, _, binding, request, _, _ = native_case
    foreign = binding.model_copy(
        update={"private_spec_ref": prep.declaration.private_input_ref}
    )
    with pytest.raises(OwnershipConflict, match="original source/input/full recovery"):
        check(native_case, binding=foreign)
    raw_spec = NavigationExecutionInput.model_validate_json(
        request.private_input
    ).spec.model_dump_json()
    with pytest.raises(ValidationError):
        check(
            native_case, request=request.model_copy(update={"private_input": raw_spec})
        )
    assert prep.state.phase == "new"
