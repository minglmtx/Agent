"""Deterministic HTTP fault peer for the actual installed PHP content reader.

This is a protocol test; it does not represent a live Admin instance or source.
"""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterator
import pytest
from urllib.parse import urlsplit
from search_http_fixtures import search_server
from test_admin_database_native import IMAGE
from test_admin_search_http import command
from lab_generate_skill.sites.shopping_admin.tasks.navigation_contents_program import (
    NAVIGATION_CONTENTS_PHP,
)

SQL = b"-- MySQL dump 10.13\n" + b"""CREATE TABLE `core_config_data` (
  `config_id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `scope` varchar(8) NOT NULL DEFAULT 'default',
  `scope_id` int(11) NOT NULL DEFAULT '0',
  `path` varchar(255) NOT NULL DEFAULT 'general',
  `value` text,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
"""
_rows: list[bytes] = []
for _engine in ("opensearch", "elasticsearch7", "elasticsearch6", "elasticsearch"):
    for _role, _value in (("hostname", "127.0.0.1"), ("port", "__PORT__")):
        _rows.append(
            f"({len(_rows)+1},'default',0,'catalog/search/{_engine}_server_{_role}','{_value}','2026-11-02 20:00:00')".encode()
        )
for _path, _value in (
    ("web/unsecure/base_url", "http://127.0.0.1:12001/"),
    ("web/secure/base_url", "http://127.0.0.1:12001/"),
    ("admin/security/password_is_forced", "0"),
    ("admin/security/password_lifetime", "0"),
    ("custom/path", "commas,backslash\\\\ and quote\\'unchanged"),
):
    _rows.append(
        f"({len(_rows)+1},'default',0,'{_path}','{_value}','{'2026-01-01 00:00:00' if _path == 'custom/path' else '2026-11-02 20:00:00'}')".encode()
    )
SQL += (
    b"INSERT INTO `core_config_data` VALUES "
    + b",".join(_rows)
    + b";\n"
    + b"INSERT INTO t VALUES (1,'unchanged');\n" * 4
)


@contextmanager
def measured_server(
    monkeypatch: pytest.MonkeyPatch, *, identity: str = "original", fault: str = "none"
) -> Iterator[tuple[Any, int]]:
    with search_server("none") as (state, port):
        state.record["cluster_uuid"] = identity + "-cluster"
        state.record["snapshot_uuid"] = identity + "-snapshot"
        calls = state.calls
        documents: list[dict[str, Any]] = [
            dict(
                _index="catalog",
                _id="1",
                _type="_doc",
                _source={"empty": {}, "number": 1, "title": "a"},
            ),
            dict(
                _index="catalog",
                _id="2",
                _type="_doc",
                _source={"empty": [], "number": 2, "title": "b"},
            ),
        ]
        if identity != "original":
            documents.reverse()
        if fault == "empty_object":
            documents[0]["_source"]["empty"] = []
        if fault == "document":
            documents[0]["_source"]["title"] = "changed"
        metadata: dict[str, Any] = dict(
            cluster_uuid=state.record["cluster_uuid"],
            cluster_uuid_committed=True,
            templates={},
            persistent_settings={},
            index_lifecycle={"operation_mode": "STOPPED"},
            repositories={
                "lab_admin_recovery": {
                    "type": "fs",
                    "uuid": "original-fixture-repository",
                    "settings": {
                        "compress": "true",
                        "location": "/state/elasticsearch/snapshots",
                    },
                    "generation": 0,
                    "pending_generation": 0,
                }
            },
            indices={
                "catalog": dict(
                    version=1,
                    settings={
                        "index": dict(
                            uuid=identity,
                            creation_date="1" if identity == "original" else "2",
                            number_of_shards="1",
                        )
                    },
                    mappings={"_doc": {"properties": {"title": {"type": "keyword"}}}},
                    aliases={},
                )
            },
        )
        if fault == "metadata":
            metadata["indices"]["catalog"]["settings"]["index"][
                "number_of_shards"
            ] = "2"

        def response(method: str, target: str) -> tuple[int, Any]:
            path = urlsplit(target).path
            calls.append((method, path))
            if path == "/":
                return 200, dict(
                    cluster_uuid=state.record["cluster_uuid"],
                    version={"number": "7.17.0"},
                )
            if path == "/_ilm/status":
                return 200, {
                    "operation_mode": "STARTED" if fault == "writer" else "STOPPED"
                }
            if path == "/_snapshot/lab_admin_recovery/baseline":
                return 200, {
                    "snapshots": [
                        dict(
                            snapshot="baseline",
                            state="SUCCESS",
                            include_global_state=True,
                            failures=[],
                            uuid=(
                                "changed"
                                if fault == "snapshot"
                                else state.record["snapshot_uuid"]
                            ),
                            version="7.17.0",
                            shards=dict(total=1, successful=1, failed=0),
                            indices=["catalog"],
                            data_streams=[],
                        )
                    ]
                }
            if path == "/_cluster/state/metadata":
                value = json.loads(json.dumps(metadata))
                if fault == "concurrent_metadata" and calls.count((method, path)) > 1:
                    value["indices"]["catalog"]["version"] = 2
                return 200, {"metadata": value}
            if path == "/_search/scroll" and method == "DELETE":
                return 200, {"succeeded": fault != "close"}
            if path.startswith("/catalog/_source/"):
                row = next(d for d in documents if d["_id"] == path.rsplit("/", 1)[-1])
                return (
                    (404, {"missing": True})
                    if fault == "missing_source"
                    else (200, row["_source"])
                )
            if path in ("/catalog/_search", "/_search/scroll"):
                hits = documents if path == "/catalog/_search" else []
                if fault == "missing_source" and hits:
                    hits = [
                        {k: v for k, v in row.items() if k != "_source"} for row in hits
                    ]
                return 200, dict(
                    _scroll_id="owned-scroll",
                    timed_out=fault == "timeout",
                    _shards=dict(
                        total=1,
                        successful=0 if fault == "shard" else 1,
                        failed=1 if fault == "shard" else 0,
                    ),
                    hits=dict(
                        total={
                            "value": 3 if fault == "count" else 2,
                            "relation": "gte" if fault == "inexact_count" else "eq",
                        },
                        hits=hits,
                    ),
                )
            return 500, {"error": "unexpected route"}

        monkeypatch.setattr(state, "response", response)
        yield state, port


def run_measurement(
    root: Path,
    port: int,
    record: dict[str, Any],
    *,
    sql: bytes | None = None,
    wrong_pin: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    root.mkdir(exist_ok=True)
    raw = SQL + b"-- Dump completed on 2026-11-02 20:00:00\n" if sql is None else sql
    raw = raw.replace(b"__PORT__", str(port).encode())
    (root / "framework-db-baseline.sql").write_bytes(raw)
    base = command(
        NAVIGATION_CONTENTS_PHP,
        str(port),
        "10",
        "0" * 64 if wrong_pin else hashlib.sha256(raw).hexdigest(),
        str(len(raw)),
        json.dumps(record, separators=(",", ":")),
        "http://127.0.0.1:12001/admin",
    )
    index = base.index(str(IMAGE))
    return subprocess.run(
        base[:index] + ("--bind", str(root) + ":/state") + base[index:],
        capture_output=True,
        timeout=20,
    )
