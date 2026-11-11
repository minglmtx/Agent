"""Declared product fixture and measured state; neither is a BaselineReceipt."""

from decimal import Decimal
import re
from typing import Literal, Self
from pydantic import Field, ValidationInfo, field_validator, model_validator
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.validation import Contract, Identifier, NonEmptyText


class ProductSeedValues(Contract):
    name: NonEmptyText
    sku: NonEmptyText
    price: str
    qty: Literal["0"]
    tax_label: Literal["Taxable Goods"]
    visibility_label: Literal["Not Visible Individually"]
    status: Literal[1]
    weight: Literal[0]
    is_in_stock: Literal[0]
    short_description: Literal[""]
    website_ids: tuple[Literal[1]]
    extra_attributes: dict[str, str]

    @field_validator("status", "weight", "is_in_stock", mode="before")
    @classmethod
    def exact_flag(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Fixture numeric flags must be integers, not booleans")
        return value

    @field_validator("website_ids", mode="before")
    @classmethod
    def exact_websites(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, (tuple, list)) or any(
            type(x) is not int for x in value
        ):
            raise ValueError("Website identifiers must be exact integers")
        if type(value) is list:
            if info.mode != "json":
                raise ValueError("Python callers must supply immutable website tuples")
            return tuple(value)
        return value

    @field_validator("price")
    @classmethod
    def decimal_price(cls, value: str) -> str:
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,7})\.[0-9]{2}", value):
            raise ValueError("Expected nonnegative fixed two-decimal fixture price")
        return value

    @field_validator("extra_attributes")
    @classmethod
    def no_target_seed(cls, value: dict[str, str]) -> dict[str, str]:
        if value:
            raise ValueError(
                "Description fixture cannot pre-populate target attributes"
            )
        return value


class ProductSeedScenario(Contract):
    scenario_id: NonEmptyText
    source_task_id: Identifier
    scope: Literal["declared_training_derivative"]
    products: tuple[ProductSeedValues]
    changes: tuple[NonEmptyText, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def same_source(self) -> Self:
        if self.scenario_id != "admin-extended-v2:" + self.source_task_id:
            raise ValueError("Fixture scenario and source identity disagree")
        return self


class ProductSeed(Contract):
    schema_version: Literal["admin-product-seed/1"] = "admin-product-seed/1"
    reference: EvidenceRef
    scenario: ProductSeedScenario

    @model_validator(mode="after")
    def private_source(self) -> Self:
        if (
            self.reference.visibility,
            self.reference.content_schema,
            self.reference.media_type,
        ) != ("private", "admin-product-fixture/1", "application/json"):
            raise ValueError("Product fixture must retain its private source reference")
        return self


class ProductState(Contract):
    schema_version: Literal["admin-product-state/1"] = "admin-product-state/1"
    product_id: int = Field(gt=0)
    store_id: Literal[0]
    sku: str
    name: str
    price: str
    qty: str
    weight: str
    tax_class_id: int = Field(ge=0)
    tax_class_label: str
    visibility: int
    status: int
    is_in_stock: bool
    website_ids: tuple[int, ...]
    category_ids: tuple[int, ...]
    url_key: str
    type_id: str
    short_description: str | None
    description: str | None

    @field_validator("price", "qty", "weight")
    @classmethod
    def decimal_fact(cls, value: str) -> str:
        if (
            not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value)
            or not Decimal(value).is_finite()
        ):
            raise ValueError("Expected exact finite decimal string")
        return value
