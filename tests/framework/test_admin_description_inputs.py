"""Selected real task input: exact public view, private scope, no readiness grant."""

import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.bootstrap.admin_description import (
    load_product_description_inputs,
)
from lab_generate_skill.adapters.plans.admin_native_input import MAX_NATIVE_BYTES
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.shopping_admin.tasks.product_description_spec import (
    ProductDescriptionInputs,
    ProductDescriptionSpec,
)

FIXTURE = Path(__file__).parent / "fixtures/admin-description-native.json"


def reference(raw: bytes, **updates: Any) -> EvidenceRef:
    values: dict[str, Any] = dict(
        uri="cas:admin-description-native",
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        media_type="application/json",
        content_schema="admin-native-contract/1",
        visibility="private",
        producer="test",
    )
    values.update(updates)
    return EvidenceRef(**values)


def public_task(**updates: Any) -> PublicTask:
    native = json.loads(FIXTURE.read_bytes())
    values: dict[str, Any] = dict(
        identity=TaskIdentity(
            source_task_id=native["source_task_id"],
            task_id="admin-description-selected-v1",
            split="train",
            site="shopping_admin",
            family="product_description",
            contract_version=1,
        ),
        goal=native["goal"],
        start_url="http://admin.example/admin" + native["start_path"],
        allowed_actions=("click", "fill"),
    )
    values.update(updates)
    return PublicTask(**values)


def changed_public(**updates: Any) -> PublicTask:
    values = public_task().model_dump()
    values.update(updates)
    return PublicTask.model_validate(values)


def load(raw: bytes) -> ProductDescriptionInputs:
    return load_product_description_inputs(raw, reference(raw), public_task())


def test_exact_historical_fixture_separates_public_and_private_without_id_conversion() -> (
    None
):
    raw = FIXTURE.read_bytes()
    original = public_task()
    result = load_product_description_inputs(raw, reference(raw), original)
    assert result.public_task == original
    assert result.private_spec.product_id == 2041
    assert result.private_spec.store_id == 0
    assert (
        result.private_spec.legacy_runtime_task_id
        == "10cdae7af1322acbc6a3@derived-6edbcfc5f6cf"
    )
    assert result.private_spec.admission == "unverified"
    assert result.private_spec.description in original.goal
    assert result.private_spec.native_contract_ref == reference(raw)
    assert (
        load(raw) == result
    )  # pure repeated binding has no mutation or status transition
    assert (
        ProductDescriptionInputs.model_validate_json(result.model_dump_json()) == result
    )
    assert set(result.public_task.model_dump()) == {
        "schema_version",
        "identity",
        "goal",
        "start_url",
        "allowed_actions",
        "output_requirements",
    }
    assert not hasattr(result, "initial_observation")
    assert not hasattr(result, "preparation_ref")


@pytest.mark.parametrize(
    "field,value",
    [
        ("control_steps", [{"private_secret": "do not send this"}]),
        ("save_steps", [{"op": "execute_private_script", "secret": "hidden"}]),
        ("derived_goal", "PRIVATE ALTERNATIVE GOAL"),
        ("revision_reason", "PRIVATE REASON"),
    ],
)
def test_private_opaque_fields_never_change_the_public_output(
    field: str, value: Any
) -> None:
    native = json.loads(FIXTURE.read_bytes())
    native["spec"][field] = value
    result = load(json.dumps(native).encode())
    assert result.public_task == public_task()
    assert "PRIVATE" not in result.public_task.model_dump_json()
    assert "private_secret" not in result.model_dump_json()
    # Scripts remain opaque inside the referenced bytes, never executable input.


@pytest.mark.parametrize(
    "field,value",
    [
        ("product_id", True),
        ("product_id", "2041"),
        ("product_id", 0),
        ("scope_id", -1),
        ("scope_id", False),
        ("scope_id", 0.0),
        ("record_id", True),
        ("record_id", 2),
        ("product_name", "Different"),
        ("source_task_id", "other"),
        ("runtime_task_id", ""),
        ("runtime_task_id", "other@derived-6edbcfc5f6cf"),
        ("runtime_task_id", "10cdae7af1322acbc6a3@derived-"),
        ("kind", "benchmark"),
        ("goal", "PRIVATE ALTERNATIVE GOAL"),
        ("status", "ready"),
        ("not_formal_training_admission", False),
        ("not_formal_training_admission", 1),
        ("evaluator_version", "v2"),
        ("start_path", "//other/"),
        ("target_path", "/wrong/"),
        ("initial_record", []),
        ("task_revision", None),
        ("spec", []),
        ("unexpected_new_semantics", True),
    ],
)
def test_invalid_native_binding_rejected(field: str, value: Any) -> None:
    native = json.loads(FIXTURE.read_bytes())
    native[field] = value
    with pytest.raises(EvidenceIntegrityError) as raised:
        load(json.dumps(native).encode())
    assert raised.value.__cause__ is not None


@pytest.mark.parametrize(
    "path,value",
    [
        (("spec", "conditions"), {}),
        (("spec", "conditions"), {"price": {"op": "equal", "value": 5}}),
        (("spec", "conditions", "description", "value"), "  "),
        (("spec", "conditions", "description", "value"), None),
        (("spec", "conditions", "description", "op"), "html"),
        (("spec", "match"), {"name": "Sony Headphones", "sku": "hidden"}),
        (("spec", "protocol"), "admin-declarative-contract-v3"),
        (("spec", "mode"), "create"),
        (("spec", "entity"), "customer"),
        (("spec", "new_semantics"), True),
        (("initial_record", "entity_id"), "2041"),
        (("initial_record", "name"), "Different"),
        (("task_revision", "runtime_goal"), "Different"),
        (("task_revision", "source_task_id"), "Different"),
    ],
)
def test_private_scope_and_lineage_conflicts_rejected(
    path: tuple[str, ...], value: Any
) -> None:
    native = json.loads(FIXTURE.read_bytes())
    parent = native
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(EvidenceIntegrityError):
        load(json.dumps(native).encode())


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b"[]",
        b"null",
        b"true",
        b"{",
        b"\xff",
        b'{"spec":{},"spec":{}}',
        b'{"spec":NaN}',
        b" " * (MAX_NATIVE_BYTES + 1),
    ],
)
def test_malformed_duplicate_nonfinite_empty_or_oversized_bytes(raw: bytes) -> None:
    with pytest.raises(EvidenceIntegrityError):
        load(raw)


@pytest.mark.parametrize("value", [None, "{}", {}, [], True, bytearray(b"{}")])
def test_wrong_raw_type(value: Any) -> None:
    with pytest.raises(EvidenceIntegrityError):
        load_product_description_inputs(value, reference(b"{}"), public_task())


@pytest.mark.parametrize(
    "updates",
    [
        {"sha256": "0" * 64},
        {"size_bytes": 1},
        {"visibility": "public"},
        {"content_schema": "different/1"},
        {"media_type": "text/plain"},
    ],
)
def test_reference_mismatch_rejected(updates: dict[str, Any]) -> None:
    raw = FIXTURE.read_bytes()
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        load_product_description_inputs(raw, reference(raw, **updates), public_task())


@pytest.mark.parametrize("suffix", ["?secret=1", "#private", "../", "x"])
def test_public_route_mismatch_rejected(suffix: str) -> None:
    raw = FIXTURE.read_bytes()
    public = changed_public(start_url=public_task().start_url + suffix)
    with pytest.raises(EvidenceIntegrityError):
        load_product_description_inputs(raw, reference(raw), public)


@pytest.mark.parametrize(
    "field,value", [("site", "shopping"), ("family", "other"), ("contract_version", 2)]
)
def test_other_family_or_version_rejected(field: str, value: Any) -> None:
    identity = public_task().identity.model_dump()
    identity[field] = value
    raw = FIXTURE.read_bytes()
    with pytest.raises(EvidenceIntegrityError):
        load_product_description_inputs(
            raw, reference(raw), changed_public(identity=identity)
        )


def test_spec_cannot_be_promoted_or_mixed_with_another_public_task() -> None:
    result = load(FIXTURE.read_bytes())
    spec = result.private_spec.model_dump()
    spec["admission"] = "approved"
    with pytest.raises(ValidationError):
        ProductDescriptionSpec.model_validate(spec)
    identity = public_task().identity.model_dump()
    identity["task_id"] = "other"
    with pytest.raises(ValidationError):
        ProductDescriptionInputs(
            public_task=changed_public(identity=identity),
            private_spec=result.private_spec,
        )
    with pytest.raises(ValidationError):
        PublicTask.model_validate(
            {**result.public_task.model_dump(), "private_spec": spec}
        )


def test_exact_size_limit_is_accepted_without_changing_original_public_text() -> None:
    raw = FIXTURE.read_bytes()
    padded = raw + b" " * (MAX_NATIVE_BYTES - len(raw))
    result = load(padded)
    assert result.public_task == public_task()
    assert result.private_spec.native_contract_ref.size_bytes == MAX_NATIVE_BYTES


@pytest.mark.parametrize(
    "description", ['A quote " and Unicode 中文 🙂\nSecond line.', "x" * 4096]
)
def test_other_product_store_and_literal_description_are_not_sample_special_cases(
    description: str,
) -> None:
    native = json.loads(FIXTURE.read_bytes())
    native["product_id"] = native["record_id"] = 37
    native["initial_record"]["entity_id"] = 37
    native["scope_id"] = 2
    native["product_name"] = native["initial_record"]["name"] = "Another product"
    native["spec"]["match"]["name"] = "Another product"
    native["spec"]["conditions"]["description"]["value"] = description
    native["goal"] = "Save the supplied description for Another product: " + description
    native["task_revision"]["runtime_goal"] = native["goal"]
    native["start_path"] = native["target_path"] = (
        "/catalog/product/edit/id/37/store/2/"
    )
    public = changed_public(
        goal=native["goal"],
        start_url="http://admin.example/admin" + native["start_path"],
    )
    raw = json.dumps(native, ensure_ascii=False).encode()
    result = load_product_description_inputs(raw, reference(raw), public)
    assert result.public_task == public
    assert (result.private_spec.product_id, result.private_spec.store_id) == (37, 2)
    assert result.private_spec.description == description
    assert result.private_spec.admission == "unverified"
