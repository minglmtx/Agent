"""Exact typed audit metadata and reverse AX checks, not model quality tests."""

from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.context_transformation import (
    ContextChange,
    ContextTransformAudit,
    context_bytes_sha,
)
from lab_generate_skill.domain.context_preparation import (
    ContextInputDraft,
    ContextPreparationReceipt,
    PreparedContextRef,
)
from lab_generate_skill.actor.context_ax_protection import diagnostic_changes
from lab_generate_skill.actor.rails_diagnostic_ax import diagnostic_ax_view
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from actor_context_projection_fixtures import actor_projection_case
from lab_generate_skill.bootstrap.context_projection import build_actor_context


def test_audit_is_mandatory_and_identity_cannot_hide_transforms() -> None:
    case = actor_projection_case()
    project, _ = build_actor_context(case.policy)
    draft = project.project(case.source, case.raw, case.policy)[0]
    value = draft.model_dump()
    del value["audit"]
    with pytest.raises(ValidationError):
        ContextInputDraft.model_validate(value)
    for update in (
        {"input_sha256": "0" * 64},
        {"role": "teacher"},
        {"policy_sha256": "0" * 64},
        {"no_op_reason": None},
    ):
        with pytest.raises(ValidationError):
            ContextInputDraft.model_validate(
                {**draft.model_dump(), "audit": {**draft.audit.model_dump(), **update}}
            )


@pytest.mark.parametrize(
    "change",
    [
        {"operation": "truncate"},
        {"source_path": ""},
        {"source_path": "/bad\0path"},
        {"target_path": "/"},
        {"target_sha256": "0" * 64},
        {"related_source_paths": ()},
        {"related_source_paths": ("/x", "/x")},
        {"source_sha256": True},
        {"extra": 1},
    ],
)
def test_illegal_transform_metadata_is_rejected(change: dict[str, object]) -> None:
    value = dict(
        operation="omit_duplicate",
        source_path="/source/1",
        target_path=None,
        source_sha256="a" * 64,
        target_sha256=None,
        related_source_paths=("/source/0",),
        reason_code="DUPLICATE",
    )
    with pytest.raises(ValidationError):
        ContextChange.model_validate({**value, **change})


SOURCE = "RootWebArea 'Example'\n\t[1] row ''\n\t\t[2] gridcell 'same 12.3 km'\n\t\t\tStaticText 'same 12.3 km'\n\t\t[3] button 'Save' disabled value='2'\n"


def test_reverse_matcher_records_all_original_omissions_and_preserves_exact_relations() -> (
    None
):
    target = diagnostic_ax_view(SOURCE).text
    changes = diagnostic_changes(SOURCE, target, target + "scope")
    assert [c.operation for c in changes] == [
        "layout",
        "remove_empty_id",
        "omit_duplicate",
    ]
    omitted = changes[-1]
    assert omitted.source_path == "/observation/text/lines/3"
    assert omitted.related_source_paths == ("/observation/text/lines/2",)
    assert omitted.source_sha256 == context_bytes_sha(
        SOURCE.splitlines(keepends=True)[3].encode()
    )


@pytest.mark.parametrize(
    "change",
    [
        "empty-id",
        "duplicate",
        "id",
        "value",
        "depth",
        "unique-leaf",
        "extra",
        "missing",
    ],
)
def test_reverse_matcher_rejects_changed_frozen_strategy_or_any_unapproved_content(
    change: str,
) -> None:
    target = diagnostic_ax_view(SOURCE).text
    edits = {
        "empty-id": ("row ''", "[1] row ''"),
        "duplicate": ("    [3]", "      StaticText 'same 12.3 km'\n    [3]"),
        "id": ("[3]", "[99]"),
        "value": ("value='2'", "value='3'"),
        "depth": ("    [3]", "  [3]"),
        "unique-leaf": ("    [3]", "      StaticText 'not a duplicate'\n    [3]"),
        "extra": ("    [3]", "    [88] link 'Extra'\n    [3]"),
        "missing": ("    [3] button 'Save' disabled value='2'\n", ""),
    }
    before, after = edits[change]
    assert before in target
    target = target.replace(before, after)
    with pytest.raises(EvidenceIntegrityError):
        diagnostic_changes(SOURCE, target, target + "scope")


def test_old_preparation_schema_is_explicitly_rejected_by_new_metadata_classes() -> (
    None
):
    assert (
        ContextPreparationReceipt.model_fields["schema_version"].default
        == "context-preparation/2"
    )
    assert (
        PreparedContextRef.model_fields["schema_version"].default
        == "prepared-context-ref/2"
    )
    with pytest.raises(ValidationError):
        ContextPreparationReceipt.model_validate_json(
            b'{"schema_version":"context-preparation/1"}'
        )
