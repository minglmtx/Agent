"""Pure selected-family binding; historical controls are opaque, never executed.

The caller must supply bytes already verified against reference. This function
validates current public identity against the supported native fields; it does
not read evidence, grant permission, create a site or produce a prepared state.
"""

from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .product_description_spec import ProductDescriptionInputs, ProductDescriptionSpec


def _object(value: object, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("Expected native object: " + name)
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected native text: " + name)
    return value


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise ValueError("Expected native integer: " + name)
    return value


def bind_product_description_inputs(
    native: dict[str, Any],
    reference: EvidenceRef,
    public_task: PublicTask,
) -> ProductDescriptionInputs:
    reference = EvidenceRef.model_validate(reference)
    public_task = PublicTask.model_validate(public_task)
    native = _object(native, "native")
    spec = _object(native.get("spec"), "spec")
    if set(native) != {
        "spec",
        "source_task_id",
        "goal",
        "kind",
        "scope_id",
        "status",
        "evaluator_version",
        "not_formal_training_admission",
        "start_path",
        "record_id",
        "initial_record",
        "target_path",
        "product_id",
        "product_name",
        "runtime_task_id",
        "task_revision",
    } or set(spec) != {
        "kind",
        "protocol",
        "mode",
        "entity",
        "match",
        "conditions",
        "control_steps",
        "save_steps",
        "derived_goal",
        "revision_reason",
    }:
        raise ValueError("Unsupported historical native fields")
    if (
        spec.get("kind"),
        spec.get("protocol"),
        spec.get("mode"),
        spec.get("entity"),
    ) != ("admin_contract", "admin-declarative-contract-v2", "update", "product"):
        raise ValueError("Unsupported native product-description contract")
    if (
        native.get("kind") != "derived"
        or native.get("evaluator_version") != "admin-declarative-contract-v3"
        or native.get("status") != "ready_for_single_attempt"
        or native.get("not_formal_training_admission") is not True
    ):
        raise ValueError("Expected the unadmitted historical derived task")
    if native.get("source_task_id") != public_task.identity.source_task_id:
        raise ValueError("Native source differs from current public identity")
    if native.get("goal") != public_task.goal:
        raise ValueError("Explicit public goal differs from original public goal")
    revision = _object(native.get("task_revision"), "task_revision")
    if (
        revision.get("version"),
        revision.get("source_task_id"),
        revision.get("runtime_goal"),
    ) != (
        "admin-derived-contract-v1",
        public_task.identity.source_task_id,
        public_task.goal,
    ):
        raise ValueError("Derived task lineage differs")
    _text(revision.get("source_goal"), "source_goal")
    _text(spec.get("revision_reason"), "revision_reason")
    match = _object(spec.get("match"), "match")
    conditions = _object(spec.get("conditions"), "conditions")
    if set(match) != {"name"} or set(conditions) != {"description"}:
        raise ValueError("Only exact product-name/description scope is supported")
    description = _object(conditions["description"], "description")
    if set(description) != {"op", "value"} or description["op"] != "plain_text":
        raise ValueError("Expected plain-text description condition")
    private = ProductDescriptionSpec(
        task=public_task.identity,
        native_contract_ref=reference,
        legacy_runtime_task_id=_text(native.get("runtime_task_id"), "runtime_task_id"),
        product_id=_integer(native.get("product_id"), "product_id"),
        store_id=_integer(native.get("scope_id"), "scope_id"),
        product_name=_text(match["name"], "product name"),
        description=_text(description["value"], "description value"),
    )
    if (
        not private.legacy_runtime_task_id.startswith(
            public_task.identity.source_task_id + "@derived-"
        )
        or private.legacy_runtime_task_id
        == public_task.identity.source_task_id + "@derived-"
    ):
        raise ValueError("Historical derived identity has different source lineage")
    initial = _object(native.get("initial_record"), "initial_record")
    if (
        type(native.get("record_id")) is not int
        or type(initial.get("entity_id")) is not int
        or native["record_id"] != private.product_id
        or initial["entity_id"] != private.product_id
        or initial.get("name") != private.product_name
        or native.get("product_name") != private.product_name
    ):
        raise ValueError("Native product identity disagrees")
    path = f"/catalog/product/edit/id/{private.product_id}/store/{private.store_id}/"
    url = urlsplit(public_task.start_url)
    if (
        native.get("start_path") != path
        or native.get("target_path") != path
        or url.path != "/admin" + path
        or url.query
        or url.fragment
    ):
        raise ValueError("Explicit public start differs from native product route")
    return ProductDescriptionInputs(public_task=public_task, private_spec=private)
