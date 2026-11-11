"""All 18 mapped category inputs, strict binding boundaries; no live rights."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
GROUP = "shopping--navigation--1c455a82597b"


def reference(raw: bytes) -> EvidenceRef:
    return evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="shopping-native-contract/1",
            visibility="private",
            producer="category-input-unit",
        ),
    )


@pytest.fixture(scope="module")
def originals() -> list[tuple[bytes, dict[str, Any], PublicTask]]:
    path = W / "docs/migration/all-task-onboarding-scope-20261102-v1/tasks.jsonl"
    with path.open() as stream:
        rows = [json.loads(line) for line in stream if GROUP in line]
    assert len(rows) == 18
    with (path.parent / "variants.jsonl").open() as stream:
        original_group = next(json.loads(line) for line in stream if GROUP in line)
    assert (
        original_group["capsule_sha256"]
        == "bb1ca9aad2be8cc75c9b89871a91313e55d324749eb463aa0be752a95a0f2fc1"
    )
    assert {row["task_key"] for row in rows} == set(original_group["members"])
    values = []
    for row in rows:
        assert row["split"] == "train" and row["site"] == "shopping"
        pin = row["contract_pin_check"]
        raw = Path(pin["path"]).read_bytes()
        assert (
            hashlib.sha256(raw).hexdigest()
            == pin["expected_sha256"]
            == pin["observed_sha256"]
        )
        native = json.loads(raw)
        public = PublicTask(
            identity=TaskIdentity(
                site="shopping",
                family="page_navigation",
                contract_version=1,
                split="train",
                task_id=row["source_task_id"],
                source_task_id=row["source_task_id"],
            ),
            goal=native["goal"],
            start_url="http://127.0.0.1:18080" + native["start_path"],
            allowed_actions=("click", "send_msg_to_user"),
        )
        values.append((raw, native, public))
    return values


def test_all_original_group_members_bind_without_goal_or_parameter_rewrite(
    originals: Any,
) -> None:
    ids = set()
    for raw, native, public in originals:
        ref = reference(raw)
        result = load_category_navigation_inputs(raw, ref, public)
        assert result == load_category_navigation_inputs(raw, ref, public)
        assert result.public_task == public
        assert result.private_spec.original.model_dump(mode="json") == native
        assert result.private_spec.native_contract_ref == ref
        assert result.private_spec.task == public.identity
        assert "admission_result" not in public.model_dump_json()
        assert "current_entry_review" not in public.model_dump_json()
        assert "heading_regex" not in public.model_dump_json()
        ids.add(result.private_spec.task.source_task_id)
    assert len(ids) == 18


@pytest.mark.parametrize(
    "field,value",
    [
        ("domain", "shopping_admin"),
        ("binding_family", "product"),
        ("task_id", "foreign"),
        ("heldout_quarantine", True),
        ("eligible_for_training", True),
        ("task_text_changed", True),
        ("heldout_quarantine", 0),
        ("api_calls", False),
        ("api_calls", 1),
        ("status", "approved"),
        ("admission_result", ""),
        ("current_entry_review", None),
        ("recorded_start_paths", []),
        ("recorded_start_paths", ["/different"]),
        ("start_path", "//foreign.test/a"),
        ("control_target_path", "/wrong"),
        ("completion", {"path_regex": "[", "heading_regex": "ok"}),
        ("completion", {"path_regex": "/", "heading_regex": ""}),
        ("completion", {"path_regex": "/", "heading_regex": "ok", "extra": True}),
    ],
)
def test_changed_native_scope_and_illegal_fields_refused(
    originals: Any, field: str, value: Any
) -> None:
    _, original, public = originals[0]
    changed = deepcopy(original)
    changed[field] = value
    raw = json.dumps(changed).encode()
    with pytest.raises(EvidenceIntegrityError):
        load_category_navigation_inputs(raw, reference(raw), public)


@pytest.mark.parametrize(
    "change", ["goal", "path", "query", "fragment", "site", "family", "source", "split"]
)
def test_foreign_public_task_refused(originals: Any, change: str) -> None:
    raw, _, public = originals[0]
    if change == "goal":
        public = public.model_copy(update={"goal": "Different public task"})
    elif change in ("path", "query", "fragment"):
        public = public.model_copy(
            update={
                "start_url": public.start_url
                + {"path": "/foreign", "query": "&foreign=1", "fragment": "#foreign"}[
                    change
                ]
            }
        )
    else:
        key = "source_task_id" if change == "source" else change
        value = {
            "site": "map",
            "family": "recorded_order_eta",
            "source": "foreign",
            "split": "dev",
        }[change]
        public = public.model_copy(
            update={"identity": public.identity.model_copy(update={key: value})}
        )
    with pytest.raises(EvidenceIntegrityError):
        load_category_navigation_inputs(raw, reference(raw), public)


@pytest.mark.parametrize(
    "raw",
    [b"", b"[]", b"null", b"true", b"{}", b'{"domain":"shopping","domain":"map"}'],
)
def test_empty_wrong_type_or_duplicate_native_refused(
    originals: Any, raw: bytes
) -> None:
    with pytest.raises(EvidenceIntegrityError):
        load_category_navigation_inputs(raw, reference(raw), originals[0][2])


def test_original_reference_bytes_and_visibility_are_still_verified(
    originals: Any,
) -> None:
    raw, _, public = originals[0]
    for ref, body in [
        (reference(raw), raw + b" "),
        (reference(raw).model_copy(update={"visibility": "public"}), raw),
        (
            reference(raw).model_copy(
                update={"content_schema": "map-native-contract/1"}
            ),
            raw,
        ),
    ]:
        with pytest.raises(EvidenceIntegrityError):
            load_category_navigation_inputs(body, ref, public)
