"""Actual pinned PHP: hidden indices/alias definitions, raw sources and cleanup."""

import hashlib
import json
import subprocess
from typing import Any
import pytest
from lab_generate_skill.sites.shopping.tasks.navigation_search_program import (
    SEARCH_CONTENTS,
)
from shopping_native_live import IMAGE
from shopping_search_inventory_http_fixtures import contents_server


def command(*args: str) -> tuple[str, ...]:
    return (
        "/usr/bin/apptainer",
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--no-mount",
        "bind-paths,hostfs,cwd",
        "--pwd",
        "/",
        str(IMAGE),
        "php",
        "-r",
        *args,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@pytest.mark.parametrize("hidden", [False, True])
def test_complete_index_set_preserves_alias_schema_raw_source_and_two_watermarks(
    hidden: bool,
) -> None:
    with contents_server(hidden=hidden) as (state, port):
        result = subprocess.run(
            command(SEARCH_CONTENTS, str(port), "10"), capture_output=True, timeout=15
        )
        assert result.returncode == 0, result.stderr.decode()
        record = json.loads(result.stdout)
        assert record["schema_version"] == "shopping-navigation-search-contents/1"
        assert set(record["indices"]) == set(state.names)
        assert record["aliases_sha256"] == digest(state.aliases())
        one = digest(["one", [], hashlib.sha256(state.source).hexdigest()])
        assert all(
            row == dict(documents=1, documents_sha256=digest([one]))
            for row in record["indices"].values()
        )
        assert record["documents"] == len(state.names)
        assert record["complete_scrolls"] and record["cleanup_confirmed"]
        assert state.stats_reads == state.alias_reads == 2
        assert sorted(state.deleted) == sorted(state.names)
        assert all(
            "expand_wildcards=all" in target
            for method, target in state.calls
            if target.startswith(("/_stats", "/_all"))
        )


@pytest.mark.parametrize(
    "fault,reason,has_scroll",
    [
        ("missing-stat-index", "watermark inventory", False),
        ("missing-primary", "primary shard", False),
        ("missing-alias-index", "alias inventory", False),
        ("extra-alias-index", "alias inventory", False),
        ("missing-alias-object", "alias definitions", False),
        ("array-alias-object", "alias definitions", False),
        ("alias-name-mismatch", "alias names", False),
        ("bad-json", "JsonException", False),
        ("changed-watermark", "changed during contents", True),
        ("changed-alias-definition", "changed during contents", True),
        ("source-http", "Incomplete search contents HTTP", True),
        ("after-scroll-http", "Incomplete search contents HTTP", True),
        ("duplicate-document", "Duplicate original document", True),
        ("cleanup-failed", "scroll cleanup unconfirmed", True),
        ("after-scroll-and-cleanup", "Incomplete search contents HTTP", True),
    ],
)
def test_incomplete_or_changed_inventory_keeps_first_error_and_original_scroll_cleanup(
    fault: str, reason: str, has_scroll: bool
) -> None:
    with contents_server(fault) as (state, port):
        result = subprocess.run(
            command(SEARCH_CONTENTS, str(port), "10"), capture_output=True, timeout=15
        )
        assert result.returncode == 2 and not result.stdout
        assert reason in result.stderr.decode()
        assert bool(state.deleted) is has_scroll
        if fault in ("cleanup-failed", "after-scroll-and-cleanup"):
            assert " | scroll cleanup:" in result.stderr.decode()


@pytest.mark.parametrize(
    "args",
    [
        ("1023", "10"),
        ("65536", "10"),
        ("x", "10"),
        ("1234", "6"),
        ("1234", "86401"),
        ("1234", "nan"),
        ("1234", "10", "extra"),
    ],
)
def test_invalid_original_endpoint_or_deadline_refused_before_http(
    args: tuple[str, ...],
) -> None:
    result = subprocess.run(
        command(SEARCH_CONTENTS, *args), capture_output=True, timeout=15
    )
    assert result.returncode == 2 and not result.stdout
    assert b"Invalid original search endpoint/budget" in result.stderr
