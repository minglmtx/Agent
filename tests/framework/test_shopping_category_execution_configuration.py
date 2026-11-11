"""Real category source/claim/owned consumers of production declarations; no live grant."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.resource_records import (
    reference as site_resource_reference,
)
from lab_generate_skill.bootstrap.shopping_category_execution_configuration import (
    prepare_category_execution_configuration,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from shopping_category_owned_fixtures import owned_navigation_case
from site_instance_fixtures import node_path as node_path
from test_shopping_category_navigation_input import originals as originals


@pytest.mark.parametrize("physical", [1, 60])
def test_actual_declarations_keep_source_site_publisher_and_independent_close_scopes(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    physical: int,
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, originals[0])
    args = dict(c.configuration_arguments, physical_close_seconds=physical)
    d = prepare_category_execution_configuration(**args)
    assert d == prepare_category_execution_configuration(**args)
    assert d.capture.schema_version == "task-capture-plan/2"
    assert (
        d.capture.close_seconds == physical and d.capture.metadata_close_seconds == 60
    )
    assert d.plan.cleanup_seconds == 60
    assert d.reset.environment_recovery_ref == args["site"].token.recovery_ref
    assert d.preparation.site_spec_ref == site_resource_reference(
        args["site"].model_dump_json().encode(), args["site"].schema_version
    )
    assert (
        d.preparation.resource_read_operation.parent_operation_id
        == args["acquisition"].operation_id
    )
    assert d.reset.parent_operation_id == d.preparation.prepare_operation.operation_id
    assert d.plan.intent == c.admitted.published.source.intent
    assert d.plan.source_ref == c.admitted.published.source_ref
    assert (
        d.preparation.private_input_ref.content_schema
        == "shopping-category-execution/1"
    )
    payload = c.source.site.evidence.read(d.preparation.private_input_ref)
    from lab_generate_skill.sites.shopping.tasks.navigation_state import (
        CategoryNavigationExecutionInput,
    )

    assert (
        CategoryNavigationExecutionInput.model_validate_json(payload).spec
        == args["private"]
    )
    assert c.owned.resources.site.phase == "new" and c.owned.resources.browser() is None


@pytest.mark.parametrize(
    "fault", ["scope", "private", "environment", "store", "operation"]
)
def test_wrong_declaration_joins_refuse_before_any_publication(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, originals[0])
    args = dict(c.configuration_arguments)
    writes: list[str] = []

    def forbidden(*values: Any, **keywords: Any) -> Any:
        writes.append("write")
        pytest.fail("Invalid declaration reached publication")

    monkeypatch.setattr(c.source.site.evidence, "put", forbidden)
    expected: type[Exception] = OwnershipConflict
    if fault == "scope":
        args["scope"] = args["scope"].model_copy(update={"attempt_id": "foreign"})
    elif fault == "private":
        spec = args["private"]
        original = spec.original
        args["private"] = spec.model_copy(
            update={
                "original": original.model_copy(
                    update={
                        "completion": original.completion.model_copy(
                            update={"heading_regex": "changed-heading"}
                        )
                    }
                )
            }
        )
    elif fault == "environment":
        args["environment"] = args["environment"].model_copy(
            update={"restore_component_id": "browser-close"}
        )
    elif fault == "store":
        args["evidence"] = object()
    elif fault == "operation":
        args["operation"] = args["operation"].model_copy(
            update={"allocation_id": "wrong-allocation"}
        )
        expected = ValueError
    with pytest.raises(expected):
        prepare_category_execution_configuration(**args)
    assert not writes


def test_invalid_limits_are_rejected_before_read_or_publication(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, originals[0])

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Invalid limits reached I/O")

    monkeypatch.setattr(c.source.site.evidence, "put", forbidden)
    monkeypatch.setattr(c.admitted.reader, "load", forbidden)
    for field, value in [
        ("metadata_cleanup_seconds", True),
        ("metadata_cleanup_seconds", 0),
        ("metadata_cleanup_seconds", 59),
        ("metadata_cleanup_seconds", 3601),
        ("physical_close_seconds", False),
        ("physical_close_seconds", 0),
        ("physical_close_seconds", 61),
        ("prefix", "x" * 101),
    ]:
        with pytest.raises(ValueError):
            prepare_category_execution_configuration(
                **dict(c.configuration_arguments, **{field: value})
            )


@pytest.mark.parametrize("when", ["before", "after"])
def test_current_claim_is_required_before_and_after_declaration_publication(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    when: str,
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, originals[0])
    writes: list[Any] = []
    put = c.source.site.evidence.put
    require = c.admitted.claims.require_source

    def recorded(*args: Any, **kwargs: Any) -> Any:
        result = put(*args, **kwargs)
        writes.append(result)
        return result

    def revoked(*args: Any, **kwargs: Any) -> Any:
        result = require(*args, **kwargs)
        if when == "before" or writes:
            raise PermissionError("Current category claim permission revoked")
        return result

    monkeypatch.setattr(c.source.site.evidence, "put", recorded)
    monkeypatch.setattr(c.admitted.claims, "require_source", revoked)
    with pytest.raises(PermissionError, match="Current category claim") as caught:
        prepare_category_execution_configuration(**c.configuration_arguments)
    if when == "before":
        assert not writes
    else:
        assert writes and tuple(writes) == getattr(
            caught.value, "category_declaration_known_references"
        )
    assert c.owned.resources.site.phase == "new"


def test_partial_publication_retains_first_error_known_and_unconfirmed_references(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, originals[0])
    put = c.source.site.evidence.put
    writes: list[Any] = []

    def lost(*args: Any, **kwargs: Any) -> Any:
        value = put(*args, **kwargs)
        writes.append(value)
        if len(writes) == 4:
            raise OSError("Declaration acknowledgement lost after CAS write")
        return value

    monkeypatch.setattr(c.source.site.evidence, "put", lost)
    with pytest.raises(OSError, match="acknowledgement lost") as caught:
        prepare_category_execution_configuration(**c.configuration_arguments)
    assert tuple(writes[:3]) == getattr(
        caught.value, "category_declaration_known_references"
    )
    assert writes[3] in getattr(caught.value, "category_declaration_candidates")
    assert len(writes) == 4 and c.owned.resources.site.phase == "new"


@pytest.mark.parametrize("value", [None, {}, [], "", 0, True])
def test_missing_original_source_and_admission_are_never_defaults(value: Any) -> None:
    with pytest.raises(TypeError, match="Original category publication"):
        prepare_category_execution_configuration(
            value,
            value,
            value,
            value,
            value,
            value,
            value,
            value,
            value,
            value,
            evidence=value,
            controls=value,
            prefix="invalid",
            metadata_cleanup_seconds=60,
            physical_close_seconds=60,
        )
