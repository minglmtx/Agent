"""Measured selected-family product records; hashes are facts, not permissions.

The protection digest covers every OTHER product under the exact legacy product
record projection, including store-0 attributes and sorted category names. It
is not a whole-database checksum, nor a copy of all raw product records.
"""

import json
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, Sha256


class ProductCatalogState(Contract):
    schema_version: Literal["admin-product-catalog-state/1"] = (
        "admin-product-catalog-state/1"
    )
    projection: Literal["legacy-admin-product-records-v1"] = (
        "legacy-admin-product-records-v1"
    )
    product_id: int = Field(gt=0)
    store_id: Literal[0]
    target_record_json: str | None = Field(max_length=262144)
    other_product_count: int = Field(ge=0, le=1000000)
    other_products_sha256: Sha256

    @model_validator(mode="after")
    def target_identity(self) -> Self:
        if self.target_record_json is None:
            return self
        raw = self.target_record_json
        if len(raw.encode()) > 262144:
            raise ValueError("Product target record exceeds byte boundary")

        def unique(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if key in result:
                    raise ValueError("Duplicate product field")
                result[key] = value
            return result

        row = json.loads(raw, object_pairs_hook=unique)
        if type(row) is not dict or not {
            "entity_id",
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
            "category_names",
        } <= set(row):
            raise ValueError("Product record is missing required measured fields")
        ident = row["entity_id"]
        if type(ident) not in (str, int) or str(ident) != str(self.product_id):
            raise ValueError("Product target identity differs")
        for key, value in row.items():
            if key == "category_names":
                if type(value) is not list or any(type(x) is not str for x in value):
                    raise ValueError("Product category names must be sorted strings")
            elif value is not None and type(value) not in (str, int):
                raise ValueError("Product fields must preserve measured scalar values")
        return self
