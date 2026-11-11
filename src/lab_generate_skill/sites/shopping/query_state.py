"""Exact original complete-query native protection and local mail contracts."""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, NonEmptyText, Sha256
from .native_static import NativeStaticPublication

PROTECTED_TABLES = frozenset(
    (
        "customer_entity",
        "customer_entity_datetime",
        "customer_entity_decimal",
        "customer_entity_int",
        "customer_entity_text",
        "customer_entity_varchar",
        "customer_address_entity",
        "customer_address_entity_datetime",
        "customer_address_entity_decimal",
        "customer_address_entity_int",
        "customer_address_entity_text",
        "customer_address_entity_varchar",
        "sales_order",
        "sales_order_item",
        "sales_order_address",
        "sales_order_payment",
        "quote_item",
        "quote_item_option",
        "salesrule",
        "salesrule_coupon",
        "salesrule_customer_group",
        "salesrule_website",
        "quote",
        "quote_address",
        "quote_payment",
        "sales_order_status_history",
        "review",
        "review_detail",
        "review_store",
        "review_entity_summary",
        "rating_option_vote",
    )
)


class ProtectedTable(Contract):
    rows: int = Field(ge=0)
    sha256: Sha256
    primary_key: tuple[NonEmptyText, ...] = Field(min_length=1)
    columns: tuple[NonEmptyText, ...] = Field(min_length=1)
    ignored_columns: tuple[str, ...] = Field(max_length=0)
    chunks: int = Field(ge=1)

    @model_validator(mode="after")
    def full_columns(self) -> Self:
        if (
            len(set(self.primary_key)) != len(self.primary_key)
            or len(set(self.columns)) != len(self.columns)
            or not set(self.primary_key) <= set(self.columns)
        ):
            raise ValueError("Exact native full-row column/key coverage required")
        return self


class QueryProtection(Contract):
    version: Literal["shopping-complete-native-query-full-rows-v1"]
    tables: dict[str, ProtectedTable]
    coverage: Literal[
        "Every row and column of explicit account/address/order/payment/cart/coupon/history/review tables. No ignored columns. Sessions, visitors, guest compare collection and authentication log are mutable runtime metadata and not claimed protected."
    ]
    statement_budget_seconds: Literal[20]

    @model_validator(mode="after")
    def full_scope(self) -> Self:
        if set(self.tables) != PROTECTED_TABLES:
            raise ValueError("All31 original Shopping query tables required")
        return self


class MailFile(Contract):
    file: NonEmptyText
    bytes: int = Field(ge=0, le=5000000)
    sha256: Sha256

    @model_validator(mode="after")
    def private_name(self) -> Self:
        if (
            str(PurePosixPath(self.file)) != self.file
            or self.file in (".", "..")
            or "/" in self.file
            or any(x in self.file for x in ("\0", "\r", "\n"))
        ):
            raise ValueError("Local mail basename required")
        return self


class LocalMail(Contract):
    backend: Literal["local_sendmail_capture_v1"]
    messages: tuple[MailFile, ...] = Field(max_length=256)
    external_delivery: Literal[False]

    @model_validator(mode="after")
    def all_messages(self) -> Self:
        names = [x.file for x in self.messages]
        if names != sorted(set(names)):
            raise ValueError("Complete distinct sorted local mail files required")
        return self


class QueryProtectedState(Contract):
    schema_version: Literal["shopping-query-protected-state/1"] = (
        "shopping-query-protected-state/1"
    )
    protection: QueryProtection
    core_fingerprint: Sha256
    native_static_assets: NativeStaticPublication
    local_mail: LocalMail
