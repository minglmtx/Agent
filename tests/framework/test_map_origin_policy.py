"""Explicit origin schema, never a source permission or an address rewrite."""

from typing import Any
import pytest
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from test_core_contracts import reference


def frozen_values() -> dict[str, Any]:
    return dict(
        mode="frozen_context",
        source_context_receipt_ref=reference("private", "public-context-receipt/1"),
        source_context_ref=reference("public", "public-construction-context/1"),
        source_start_url="http://127.0.0.1:20001/search?q=A%20B#map=12/1/2",
    )


def test_exact_origin_roundtrip_dynamic_and_no_implicit_defaults() -> None:
    dynamic = MapOriginPolicy.dynamic()
    assert dynamic.requested_web_port is None
    assert MapOriginPolicy.model_validate_json(dynamic.model_dump_json()) == dynamic
    frozen = MapOriginPolicy(**frozen_values())
    assert frozen.requested_web_port == 20001
    assert frozen.source_start_url == frozen_values()["source_start_url"]
    assert MapOriginPolicy.model_validate_json(frozen.model_dump_json()) == frozen
    for field in frozen_values():
        missing = frozen_values()
        missing.pop(field)
        with pytest.raises(ValueError):
            MapOriginPolicy.model_validate(missing)


@pytest.mark.parametrize("bad", [None, "", [], {}, 1, True])
def test_empty_wrong_type_or_missing_policy_is_rejected(bad: Any) -> None:
    with pytest.raises(ValueError):
        MapOriginPolicy.model_validate(bad)


@pytest.mark.parametrize("field", list(frozen_values())[1:])
def test_dynamic_cannot_claim_source_and_frozen_cannot_omit_it(field: str) -> None:
    dynamic = MapOriginPolicy.dynamic().model_dump()
    dynamic[field] = frozen_values()[field]
    with pytest.raises(ValueError):
        MapOriginPolicy.model_validate(dynamic)
    values = frozen_values()
    values[field] = None
    with pytest.raises(ValueError):
        MapOriginPolicy.model_validate(values)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://localhost:20001/",
        "https://127.0.0.1:20001/",
        "http://127.0.0.2:20001/",
        "http://127.0.0.1/",
        "http://127.0.0.1:80/",
        "http://127.0.0.1:65536/",
        "http://127.0.0.1:020001/",
        "http://user@127.0.0.1:20001/",
        "http://127.0.0.1:20001/\n",
        "http://127.0.0.1:20001/a b",
        "http://127.0.0.1:20001/" + "x" * 4096,
    ],
)
def test_noncanonical_or_illegal_source_url_is_not_normalized(url: str) -> None:
    with pytest.raises(ValueError):
        MapOriginPolicy(**{**frozen_values(), "source_start_url": url})


@pytest.mark.parametrize(
    "field,reference_value",
    [
        ("source_context_receipt_ref", reference("public", "public-context-receipt/1")),
        ("source_context_receipt_ref", reference("private", "wrong/1")),
        ("source_context_ref", reference("private", "public-construction-context/1")),
        ("source_context_ref", reference("public", "wrong/1")),
    ],
)
def test_source_roles_and_schemas_remain_distinct(
    field: str, reference_value: Any
) -> None:
    with pytest.raises(ValueError):
        MapOriginPolicy(**{**frozen_values(), field: reference_value})
