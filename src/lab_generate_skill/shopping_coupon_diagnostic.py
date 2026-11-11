"""Private complete protected-row diagnosis; no mutation or normal admission.

Column values and primary-key values never leave the native reader. Comparisons
retain the exact existing 22-table protection scope and its one declared
quote_item.updated_at metadata exclusion.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

VERSION = "shopping-coupon-cleanup-diagnostic-v1"
SNAPSHOT_VERSION = "shopping-coupon-protected-column-hashes-v1"
TABLES = (
    "customer_entity", "customer_entity_datetime", "customer_entity_decimal",
    "customer_entity_int", "customer_entity_text", "customer_entity_varchar",
    "customer_address_entity", "customer_address_entity_datetime",
    "customer_address_entity_decimal", "customer_address_entity_int",
    "customer_address_entity_text", "customer_address_entity_varchar",
    "sales_order", "sales_order_item", "sales_order_address", "sales_order_payment",
    "quote_item", "quote_item_option", "salesrule", "salesrule_coupon",
    "salesrule_customer_group", "salesrule_website",
)
_SHA = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def _sha(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError("Invalid protected native hash")
    return value


def validate_snapshot(value):
    if not isinstance(value, dict) or value.get("version") != SNAPSHOT_VERSION:
        raise ValueError("Unsupported complete native protected snapshot")
    if type(value.get("cart_id")) is not int or value["cart_id"] <= 0:
        raise ValueError("Positive native cart identity required")
    if value.get("statement_budget_seconds") != 20 or value.get("keyset_page_size") != 1024:
        raise ValueError("Native protected reader budget changed")
    tables = value.get("tables")
    if not isinstance(tables, dict) or set(tables) != set(TABLES):
        raise ValueError("All 22 declared protected tables required")
    for table, data in tables.items():
        if not isinstance(data, dict):
            raise ValueError("Protected table snapshot must be an object")
        count = data.get("rows")
        if type(count) is not int or count < 0:
            raise ValueError("Exact full-row count required")
        columns, primary = data.get("columns"), data.get("primary_key")
        if not isinstance(columns, list) or not columns or len(set(columns)) != len(columns):
            raise ValueError("Exact unique native columns required")
        if any(not isinstance(k, str) or not _IDENTIFIER.fullmatch(k) for k in columns):
            raise ValueError("Invalid native column name")
        if not isinstance(primary, list) or not primary or len(set(primary)) != len(primary) or not set(primary) <= set(columns):
            raise ValueError("Exact native primary key required")
        ignored = ["updated_at"] if table == "quote_item" else []
        if data.get("ignored_columns") != ignored or not set(ignored) <= set(columns):
            raise ValueError("Protected column exclusions changed")
        _sha(data.get("sha256"))
        if type(data.get("chunks")) is not int or data["chunks"] < 1:
            raise ValueError("Complete native keyset iteration required")
        index = data.get("row_index")
        if not isinstance(index, dict) or len(index) != count:
            raise ValueError("Full row identities required, not a sample")
        cart_keys = data.get("current_cart_row_keys")
        if not isinstance(cart_keys, list) or len(set(cart_keys)) != len(cart_keys):
            raise ValueError("Exact diagnostic cart membership required")
        if table not in ("quote_item", "quote_item_option") and cart_keys:
            raise ValueError("Cart membership on a non-cart table")
        if not set(cart_keys) <= set(index):
            raise ValueError("Cart membership must reference captured rows")
        for key, row in index.items():
            _sha(key)
            if not isinstance(row, dict):
                raise ValueError("Protected row hash must be an object")
            _sha(row.get("sha256"))
            fields = row.get("column_sha256")
            metadata = row.get("ignored_column_sha256")
            if not isinstance(fields, dict) or set(fields) != set(columns) - set(ignored):
                raise ValueError("Every protected column must be captured")
            if not isinstance(metadata, dict) or set(metadata) != set(ignored):
                raise ValueError("Ignored metadata must remain explicitly separate")
            for field_hash in (*fields.values(), *metadata.values()):
                _sha(field_hash)
    return value


def protected_summary(value):
    validate_snapshot(value)
    return {
        name: {k: deepcopy(data[k]) for k in
               ("rows", "sha256", "primary_key", "columns", "ignored_columns", "chunks")}
        for name, data in value["tables"].items()
    }


def compare_snapshots(before, after):
    """Exact safe per-field evidence, including foreign rows and schema changes."""
    validate_snapshot(before)
    validate_snapshot(after)
    if before["cart_id"] != after["cart_id"]:
        raise ValueError("Diagnostic cart identity changed")
    changes, metadata = [], []
    for name in TABLES:
        old, new = before["tables"][name], after["tables"][name]
        for schema in ("primary_key", "columns", "ignored_columns"):
            if old[schema] != new[schema]:
                raise ValueError("Protected native schema changed")
        index_a, index_b = old["row_index"], new["row_index"]
        cart_keys = set(old["current_cart_row_keys"]) | set(new["current_cart_row_keys"])
        for key in sorted(set(index_a) | set(index_b)):
            a, b = index_a.get(key), index_b.get(key)
            if a is None or b is None:
                changes.append({
                    "table": name, "row_key_sha256": key,
                    "kind": "added" if a is None else "removed",
                    "current_cart_row": key in cart_keys,
                    "before_row_sha256": None if a is None else a["sha256"],
                    "after_row_sha256": None if b is None else b["sha256"],
                    "columns": [],
                })
                continue
            fields = [
                {"column": column, "before_sha256": a["column_sha256"][column],
                 "after_sha256": b["column_sha256"][column]}
                for column in old["columns"] if column not in old["ignored_columns"]
                and a["column_sha256"][column] != b["column_sha256"][column]
            ]
            if bool(fields) != (a["sha256"] != b["sha256"]):
                raise ValueError("Native protected row and column hashes disagree")
            if fields:
                changes.append({
                    "table": name, "row_key_sha256": key, "kind": "changed",
                    "current_cart_row": key in cart_keys,
                    "before_row_sha256": a["sha256"], "after_row_sha256": b["sha256"],
                    "columns": fields,
                })
            for column in old["ignored_columns"]:
                if a["ignored_column_sha256"][column] != b["ignored_column_sha256"][column]:
                    metadata.append({
                        "table": name, "row_key_sha256": key, "column": column,
                        "before_sha256": a["ignored_column_sha256"][column],
                        "after_sha256": b["ignored_column_sha256"][column],
                        "excluded_by_original_protection_protocol": True,
                    })
        table_same = (old["rows"], old["sha256"]) == (new["rows"], new["sha256"])
        relevant = any(c["table"] == name for c in changes)
        if table_same == relevant:
            raise ValueError("Native table and full row indexes disagree")
    return {
        "complete_declared_protected_rows_equal": not changes,
        "changed_tables": [name for name in TABLES if any(c["table"] == name for c in changes)],
        "protected_row_changes": changes,
        "declared_metadata_changes": metadata,
        "raw_values_or_credentials_saved": False,
    }


def capture_snapshot(site, cart_id, *, progress_path=None):
    if type(cart_id) is not int or cart_id <= 0:
        raise ValueError("Positive native cart identity required")
    path = Path(__file__).with_name("shopping_coupon_diagnostic.php")
    try:
        response = site.command(
            ["php", "-d", "memory_limit=1024M", "-r",
             path.read_text().removeprefix("<?php"), str(cart_id)],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as exc:
        _save_progress(getattr(exc, "stderr", "") or "", progress_path)
        raise
    _save_progress(response.stderr or "", progress_path)
    return validate_snapshot(json.loads(response.stdout))


def _save_progress(stderr, path):
    if path is None:
        return
    records = []
    for line in stderr.splitlines():
        if line.startswith("LAB_COUPON_PROTECTED_PROGRESS "):
            value = json.loads(line.removeprefix("LAB_COUPON_PROTECTED_PROGRESS "))
            if (not isinstance(value, dict) or value.get("table") not in TABLES
                    or type(value.get("rows")) is not int or type(value.get("chunk")) is not int):
                raise ValueError("Malformed safe native protected progress")
            records.append({k: value[k] for k in ("table", "rows", "chunk")})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(records, indent=2) + "\n")


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
