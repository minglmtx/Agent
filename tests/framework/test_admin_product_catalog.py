"""Exact bounded product capture, no missing-state or transport fallback."""

import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.sites.shopping_admin.product_catalog import (
    capture_product_catalog,
    ProductCatalogReplyError,
)
from lab_generate_skill.sites.shopping_admin.product_catalog_contract import (
    ProductCatalogState,
)
from lab_generate_skill.sites.shopping_admin.product_catalog_program import (
    PRODUCT_RECORDS_SQL,
    PRODUCT_ATTRIBUTES_SQL,
    PRODUCT_CATALOG_PHP,
)
from test_admin_product_seed import Commands
from test_admin_services import spec
from test_slurm_commands import guard


def state(**updates: Any) -> ProductCatalogState:
    row: dict[str, Any] = {
        key: None
        for key in (
            "sku",
            "name",
            "price",
            "special_price",
            "status",
            "country_of_manufacture",
            "qty",
            "is_in_stock",
            "backorders",
            "use_config_backorders",
        )
    }
    row.update(entity_id="2041", name="Sony Headphones", category_names=[])
    return ProductCatalogState.model_validate(
        (
            dict(
                product_id=2041,
                store_id=0,
                target_record_json=json.dumps(row),
                other_product_count=2,
                other_products_sha256="a" * 64,
            )
            | updates
        )
    )


def test_original_capture_and_absent_target_are_distinct(tmp_path: Path) -> None:
    commands = Commands()
    for expected in (state(), state(target_record_json=None, other_product_count=0)):
        commands.reply = expected.model_dump_json().encode()
        assert (
            capture_product_catalog(spec(tmp_path), 2041, commands, guard()) == expected
        )
        assert commands.calls[-1][-4:] == ("php", "-r", PRODUCT_CATALOG_PHP, "2041")
    assert len(commands.calls) == 2


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "2041", None, 10000000000])
def test_invalid_id_never_invokes_native_reader(tmp_path: Path, value: Any) -> None:
    commands = Commands()
    with pytest.raises(ValueError):
        capture_product_catalog(spec(tmp_path), value, commands, guard())
    assert commands.calls == []


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"null",
        b"[]",
        b"not-json",
        state(product_id=2042, target_record_json=None).model_dump_json().encode(),
        state().model_dump_json().encode() + b"\n",
    ],
)
def test_invalid_reply_retains_bytes_and_does_not_retry(
    tmp_path: Path, raw: bytes
) -> None:
    commands = Commands()
    commands.reply = raw
    with pytest.raises(ProductCatalogReplyError) as caught:
        capture_product_catalog(spec(tmp_path), 2041, commands, guard())
    assert caught.value.raw_reply == raw and caught.value.__cause__ is not None
    assert len(commands.calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"store_id": 1},
        {"other_product_count": -1},
        {"other_products_sha256": "bad"},
        {"target_record_json": "{}"},
        {"target_record_json": '{"entity_id":"2041","entity_id":"2041"}'},
        {"target_record_json": "x" * 262145},
    ],
)
def test_invalid_capture_shape_is_not_zero_or_empty(change: dict[str, Any]) -> None:
    with pytest.raises((ValueError, ValidationError)):
        state(**change)


def test_native_failure_keeps_primary_and_single_attempt(tmp_path: Path) -> None:
    commands = Commands()
    failure = OSError("native unavailable")
    commands.error = failure
    with pytest.raises(OSError) as caught:
        capture_product_catalog(spec(tmp_path), 2041, commands, guard())
    assert caught.value is failure and len(commands.calls) == 1


def test_exact_legacy_product_query_and_attribute_projection() -> None:
    legacy = (
        Path(__file__).parent / "fixtures/admin-legacy-product-probe.php"
    ).read_text()
    assert 'queryRows("' + PRODUCT_RECORDS_SQL + '")' in legacy
    assert (
        PRODUCT_ATTRIBUTES_SQL.replace(
            "catalog_product_entity_{$backend}",
            "catalog_{$entityKind}_entity_{$backend}",
        )
        in legacy
    )
    assert (
        "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY" in PRODUCT_CATALOG_PHP
    )
    assert "mysql:unix_socket=" in PRODUCT_CATALOG_PHP
