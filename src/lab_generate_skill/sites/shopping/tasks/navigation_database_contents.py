"""Complete pinned Shopping SQL contents; physical origin remains in the proof.

Only original startup web/search values are normalized. All370 table schemas and
all row bytes are retained as hashes. The original session/visitor runtime rows
remain recorded, outside comparison; no recovery or query protection is narrowed.
This database component alone is not a complete initial-equivalence proof.
"""

import hashlib
import json
from urllib.parse import urlsplit
from typing import Literal, Self
from pydantic import Field, model_validator
from lab_generate_skill.domain.validation import Contract, NonEmptyText, Sha256
from ..service_contract import ShoppingServiceSpec

TABLE_NAMES_SHA256 = "f9d2f3065ebd472d73446bdbed661f302948ed264be8d2f32d7715c8f8a7c339"
ORIGINAL_IMAGE_SHA256 = (
    "455ec7d98aa89b7b63b627aea567f91816d75da50bd160f5db2cc1dfe52f6812"
)
RUNTIME_ROW_TABLES = ("customer_visitor", "session")
CONFIGURED_PATHS = tuple(
    sorted(
        (
            "web/unsecure/base_url",
            "web/secure/base_url",
            *(
                "catalog/search/" + engine + "_server_" + suffix
                for engine in (
                    "opensearch",
                    "elasticsearch7",
                    "elasticsearch6",
                    "elasticsearch",
                )
                for suffix in ("hostname", "port")
            ),
        )
    )
)


class NavigationDatabaseTable(Contract):
    kind: Literal["BASE TABLE", "VIEW"]
    columns: tuple[NonEmptyText, ...] = Field(min_length=1, max_length=1024)
    rows: int = Field(ge=0, le=20_000_000)
    schema_sha256: Sha256
    raw_schema_sha256: Sha256
    raw_rows_sha256: Sha256
    content_rows_sha256: Sha256

    @model_validator(mode="after")
    def distinct_columns(self) -> Self:
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("Complete distinct original SQL columns required")
        return self


class NavigationDatabaseContents(Contract):
    schema_version: Literal["shopping-navigation-database-contents/2"] = (
        "shopping-navigation-database-contents/2"
    )
    table_names_sha256: Literal[
        "f9d2f3065ebd472d73446bdbed661f302948ed264be8d2f32d7715c8f8a7c339"
    ]
    normalization: Literal["original-shopping-startup-endpoints-and-counters-v2"]
    runtime_row_tables: tuple[Literal["customer_visitor", "session"], ...]
    web_endpoint: NonEmptyText
    search_port: int = Field(ge=1024, le=65535)
    configured_paths: tuple[NonEmptyText, ...]
    tables: dict[str, NavigationDatabaseTable] = Field(min_length=370, max_length=370)
    read_only_consistent_transaction: Literal[True]

    @model_validator(mode="after")
    def complete(self) -> Self:
        endpoint = urlsplit(self.web_endpoint)
        if (
            endpoint.port is None
            or not 1024 <= endpoint.port <= 65535
            or self.web_endpoint != f"http://127.0.0.1:{endpoint.port}/"
        ):
            raise ValueError("Original loopback web endpoint required")
        names = sorted(self.tables)
        observed = hashlib.sha256(
            json.dumps(names, separators=(",", ":")).encode()
        ).hexdigest()
        if (
            observed != TABLE_NAMES_SHA256
            or self.runtime_row_tables != RUNTIME_ROW_TABLES
            or self.configured_paths != CONFIGURED_PATHS
        ):
            raise ValueError(
                "Exact pinned370 tables and original endpoint/runtime policy required"
            )
        if any(
            table.raw_rows_sha256 != table.content_rows_sha256
            for name, table in self.tables.items()
            if name != "core_config_data"
        ):
            raise ValueError(
                "Only verified original core configuration values may normalize"
            )
        if any(
            table.raw_schema_sha256 != table.schema_sha256
            for name, table in self.tables.items()
            if name not in (*RUNTIME_ROW_TABLES, "core_config_data")
        ):
            raise ValueError(
                "Only original startup/runtime counter options may normalize"
            )
        return self

    def require_service(self, spec: ShoppingServiceSpec) -> None:
        spec = ShoppingServiceSpec.model_validate(spec)
        if spec.files.image.sha256 != ORIGINAL_IMAGE_SHA256 or (
            self.web_endpoint,
            self.search_port,
        ) != (spec.endpoint, spec.ports.search):
            raise ValueError(
                "SQL measurement changed original physical service endpoints"
            )

    @property
    def content_sha256(self) -> str:
        tables = {
            name: table.model_dump(
                mode="json",
                exclude=(
                    {
                        "rows",
                        "raw_rows_sha256",
                        "content_rows_sha256",
                        "raw_schema_sha256",
                    }
                    if name in RUNTIME_ROW_TABLES
                    else {"raw_rows_sha256", "raw_schema_sha256"}
                ),
            )
            for name, table in sorted(self.tables.items())
        }
        value = {
            "schema_version": self.schema_version,
            "normalization": self.normalization,
            "runtime_row_tables": self.runtime_row_tables,
            "table_names_sha256": self.table_names_sha256,
            "tables": tables,
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
