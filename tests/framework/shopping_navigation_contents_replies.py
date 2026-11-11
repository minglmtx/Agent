"""Explicit complete-content replies for existing synthetic native effects.

No PHP/native service runs here. Actual fixed producers have separate scoped
receipts; this double only connects their strict output formats to consumers.
"""

import hashlib
import json
from pathlib import Path
from typing import Any


def database_reply(endpoint: str, search_port: int, different: bool = False) -> bytes:
    from lab_generate_skill.sites.shopping.tasks.navigation_database_contents import (
        CONFIGURED_PATHS,
    )

    names = json.loads(
        Path(__file__)
        .with_name("fixtures")
        .joinpath("shopping-native-content-scope.json")
        .read_text()
    )["table_names"]
    tables: dict[str, Any] = {}
    for name in names:
        schema = hashlib.sha256(name.encode()).hexdigest()
        row = "b" * 64 if different and name == "catalog_category_entity" else "a" * 64
        tables[name] = {
            "kind": "BASE TABLE",
            "columns": ["id", "value"],
            "rows": 1,
            "schema_sha256": schema,
            "raw_schema_sha256": schema,
            "raw_rows_sha256": row,
            "content_rows_sha256": row,
        }
    return json.dumps(
        {
            "schema_version": "shopping-navigation-database-contents/2",
            "table_names_sha256": "f9d2f3065ebd472d73446bdbed661f302948ed264be8d2f32d7715c8f8a7c339",
            "normalization": "original-shopping-startup-endpoints-and-counters-v2",
            "runtime_row_tables": ["customer_visitor", "session"],
            "web_endpoint": endpoint,
            "search_port": search_port,
            "configured_paths": list(CONFIGURED_PATHS),
            "tables": tables,
            "read_only_consistent_transaction": True,
        }
    ).encode()


def search_reply(port: int, different: bool = False) -> bytes:
    return json.dumps(
        {
            "schema_version": "shopping-navigation-search-contents/1",
            "search_port": port,
            "cluster_uuid": "original-cluster",
            "version": "7.17.0",
            "normalization": "original-shopping-search-physical-identity-v1",
            "raw_metadata_sha256": "a" * 64,
            "metadata_sha256": "b" * 64,
            "aliases_sha256": "c" * 64,
            "mutation_watermark_sha256": "d" * 64,
            "indices": {
                "catalog": {
                    "documents": 1,
                    "documents_sha256": ("b" if different else "a") * 64,
                }
            },
            "documents": 1,
            "complete_scrolls": True,
            "cleanup_confirmed": True,
        }
    ).encode()


def file_reply(inventory_json: str, ports: list[int]) -> bytes:
    raw = json.loads(inventory_json)
    included = {k: raw[k] for k in ("files", "directories", "bytes")}
    included["raw_sha256"] = "a" * 64
    empty = {"files": 0, "directories": 0, "bytes": 0, "raw_sha256": "a" * 64}
    return json.dumps(
        {
            "schema_version": "shopping-navigation-file-contents/1",
            "normalization": "original-shopping-category-files-and-endpoints-v1",
            "inventory": raw,
            "ports": ports,
            "sections": {
                "included": included,
                "database": empty.copy(),
                "search": empty.copy(),
                "runtime": empty.copy(),
            },
            "content_sha256": "c" * 64,
            "snapshot_read_only": True,
            "configuration_executed": False,
        }
    ).encode()
