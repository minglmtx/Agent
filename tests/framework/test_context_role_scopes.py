"""Teacher run-level operations cannot fabricate Actor attempt identities."""

from pathlib import Path
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.context_preparation import ContextPreparationRequest
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.teacher_scope import TeacherContextScope
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.application.context_preparation import prepare_context
from lab_generate_skill.application.context_review import review_context
from teacher_context_fixtures import teacher_preparation_case
from test_slurm_commands import guard

FIXTURE = (
    Path(__file__).parent / "fixtures/actor-context-preparation-request-4859004.json"
)


def test_saved_original_actor_v1_preparation_keeps_exact_canonical_bytes() -> None:
    raw = FIXTURE.read_bytes()
    request = ContextPreparationRequest.model_validate_json(raw)
    assert request.model_dump_json().encode() == raw
    assert request.schema_version == "context-preparation-request/1" and isinstance(
        request.scope, StateScope
    )
    assert request.operation.attempt_id == request.scope.attempt_id
    assert request.source.role == "actor"
    assert ContextPreparationRequest.model_validate(request) == request


def test_teacher_task_scope_v2_prepare_and_review_preserve_original_run_level_without_attempt(
    tmp_path: Path,
) -> None:
    c = teacher_preparation_case(tmp_path / "source")
    request = c.request
    assert isinstance(request.scope, TeacherContextScope) and not hasattr(
        request.scope, "attempt_id"
    )
    assert request.schema_version == "context-preparation-request/2"
    assert all(
        value is None
        for value in (
            request.operation.attempt_id,
            request.operation.allocation_id,
            request.operation.recovery_ref,
        )
    )
    assert (
        ContextPreparationRequest.model_validate_json(request.model_dump_json())
        == request
    )
    prepared = prepare_context(request, c.deps(), control=guard())
    receipt = review_context(
        request,
        prepared,
        c.review_deps(),
        expected_input_ref=prepared.selected_input_ref,
        control=guard(),
    )
    assert receipt.request == request and receipt.outcome == "prepared"


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt_id", "another-attempt"),
        ("allocation_id", "actor"),
        ("owner_id", "foreign"),
        ("run_id", "foreign"),
        ("mode", "cleanup"),
    ],
)
def test_task_teacher_cannot_borrow_actor_or_other_run_operations(
    tmp_path: Path, field: str, value: str
) -> None:
    c = teacher_preparation_case(tmp_path / "source")
    op = {**c.request.operation.model_dump(), field: value}
    if field == "mode":
        op["parent_operation_id"] = "original"
    with pytest.raises((OwnershipConflict, ValueError)):
        ContextPreparationRequest.model_validate(
            {**c.request.model_dump(), "operation": op}
        )
    assert c.counter.calls == 0


def test_explicit_scope_schema_versions_and_role_are_not_silently_migrated(
    tmp_path: Path,
) -> None:
    c = teacher_preparation_case(tmp_path / "source")
    with pytest.raises(ValueError):
        ContextPreparationRequest.model_validate(
            {
                **c.request.model_dump(),
                "schema_version": "context-preparation-request/1",
            }
        )
    actor = ContextPreparationRequest.model_validate_json(FIXTURE.read_bytes())
    with pytest.raises(ValueError):
        ContextPreparationRequest.model_validate(
            {**actor.model_dump(), "schema_version": "context-preparation-request/2"}
        )
    with pytest.raises(OwnershipConflict):
        ContextPreparationRequest.model_validate(
            {
                **actor.model_dump(),
                "schema_version": "context-preparation-request/2",
                "scope": c.request.scope,
                "operation": c.request.operation,
            }
        )
    for attempt in (None, "fresh-id"):
        with pytest.raises(ValidationError):
            TeacherContextScope.model_validate_json(
                json.dumps(
                    {**c.request.scope.model_dump(mode="json"), "attempt_id": attempt}
                )
            )
    bad = actor.scope.model_dump(mode="json")
    bad["attempt_id"] = None
    with pytest.raises(ValidationError):
        StateScope.model_validate_json(json.dumps(bad))
