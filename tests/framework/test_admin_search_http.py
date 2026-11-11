"""Actual pinned PHP against deterministic HTTP faults before costly site startup."""

import json
from pathlib import Path
import subprocess
import pytest
from lab_generate_skill.sites.shopping_admin.search_program import SEARCH_SNAPSHOT_PHP
from test_admin_search_native import PROBE
from test_admin_database_native import IMAGE
from search_http_fixtures import search_server


def command(program: str, *args: str) -> tuple[str, ...]:
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
        program,
        *args,
    )


@pytest.mark.parametrize(
    "program", [SEARCH_SNAPSHOT_PHP, PROBE], ids=["search", "fixture"]
)
def test_fixed_native_program_syntax_before_services(program: str) -> None:
    result = subprocess.run(
        command("if(false){" + program + "}"), capture_output=True, timeout=15
    )
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize("mode", ["verify", "restore"])
def test_native_http_uses_original_snapshot_and_exact_index_names(mode: str) -> None:
    with search_server("none") as (state, port):
        result = subprocess.run(
            command(
                SEARCH_SNAPSHOT_PHP,
                str(port),
                "10",
                mode,
                json.dumps(state.record, separators=(",", ":")),
            ),
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr.decode()
        out = json.loads(result.stdout)
        assert out["snapshot"] == state.record and out["operation"] == mode
        assert state.deleted == ([] if mode == "verify" else ["catalog", "extra"])
        assert len(
            [
                x
                for x in state.calls
                if x == ("POST", "/_snapshot/lab_admin_recovery/baseline/_restore")
            ]
        ) == (0 if mode == "verify" else 1)


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_repository",
        "partial_snapshot",
        "wrong_snapshot",
        "snapshot_http",
        "snapshot_missing",
        "unsupported_version",
        "wildcard",
        "duplicates",
        "closed_index",
        "delete_failure",
        "delete_unconfirmed",
        "cluster_changed",
        "restore_failure",
        "failed_shard",
        "red_health",
        "health_timeout",
        "wrong_final_indices",
        "bad_json",
        "oversize",
    ],
)
def test_native_failures_preserve_deleted_prefix_and_do_not_retry(fault: str) -> None:
    with search_server(fault) as (state, port):
        result = subprocess.run(
            command(
                SEARCH_SNAPSHOT_PHP,
                str(port),
                "10",
                "restore",
                json.dumps(state.record, separators=(",", ":")),
            ),
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 2, (result.stdout, result.stderr)
        # Runtime warnings may precede the structured final original error.
        error = json.loads(result.stderr.splitlines()[-1])
        assert error["deleted_indices"] == (
            [] if fault == "delete_unconfirmed" else state.deleted
        )
        assert error["attempted_deletions"] == [
            path[1:] for method, path in state.calls if method == "DELETE"
        ]
        assert len(state.deleted) == len(set(state.deleted))
        attempts = [c for c in state.calls if c[0] in ("POST", "DELETE")]
        assert len(attempts) == len(set(attempts))
        if fault in (
            "wrong_repository",
            "partial_snapshot",
            "wrong_snapshot",
            "snapshot_http",
            "snapshot_missing",
            "unsupported_version",
            "wildcard",
            "duplicates",
            "closed_index",
            "bad_json",
            "oversize",
        ):
            assert not state.deleted and not attempts
        if fault == "delete_failure":
            assert state.deleted == ["catalog"] and not state.restored
        if fault == "restore_failure":
            assert state.deleted == ["catalog", "extra"] and not state.restored


def test_original_http_deadline_has_no_retry() -> None:
    with search_server("blocked") as (state, port):
        result = subprocess.run(
            command(
                SEARCH_SNAPSHOT_PHP,
                str(port),
                "0.1",
                "restore",
                json.dumps(state.record, separators=(",", ":")),
            ),
            capture_output=True,
            timeout=5,
        )
        assert result.returncode == 2
        error = json.loads(result.stderr.splitlines()[-1])
        assert error["attempted_deletions"] == [] and state.calls == [("GET", "/")]


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "stream_unconfirmed",
        "stream_wrong_member",
        "stream_duplicate",
        "ilm_running",
        "ilm_invalid",
    ],
)
def test_stream_write_index_and_ilm_preflight(fault: str) -> None:
    with search_server(fault) as (state, port):
        state.indices = [".ds-events-000001", "catalog", "extra"]
        state.streams = {"events": [".ds-events-000001"]}
        state.record.update(
            indices=[".ds-events-000001", "catalog"], data_streams=["events"]
        )
        if fault == "stream_wrong_member":
            state.streams["events"] = ["missing"]
        if fault == "stream_duplicate":
            state.streams["events"] *= 2
        if fault.startswith("ilm_"):
            state.ilm = "RUNNING" if fault == "ilm_running" else "invalid"
        result = subprocess.run(
            command(
                SEARCH_SNAPSHOT_PHP,
                str(port),
                "10",
                "restore",
                json.dumps(state.record, separators=(",", ":")),
            ),
            capture_output=True,
            timeout=15,
        )
        if fault == "none":
            assert result.returncode == 0, result.stderr.decode()
            assert state.deleted_streams == ["events"]
            assert state.deleted == ["catalog", "extra"]
            assert json.loads(result.stdout)["snapshot"] == state.record
            assert state.streams == {"events": [".ds-events-000001"]}
        else:
            assert result.returncode == 2, result.stdout
            error = json.loads(result.stderr.splitlines()[-1])
            if fault == "stream_unconfirmed":
                assert error["attempted_stream_deletions"] == ["events"]
                assert error["deleted_streams"] == [] and state.deleted_streams == [
                    "events"
                ]
            else:
                assert not [call for call in state.calls if call[0] != "GET"]
            assert not state.deleted and not state.restored
        assert ("DELETE", "/.ds-events-000001") not in state.calls


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "stop_unconfirmed",
        "ilm_stuck",
        "repository_exists",
        "save_inventory_changed",
        "save_streams_changed",
        "partial_snapshot",
    ],
)
def test_native_save_stops_ilm_once_and_checks_snapshot_inventory(
    tmp_path: Path, fault: str
) -> None:
    with search_server(fault) as (state, port):
        state.repository_exists = fault == "repository_exists"
        state.ilm = "RUNNING"
        state.indices = [".ds-events-000001", "catalog"]
        state.streams = {"events": [".ds-events-000001"]}
        state.record.update(indices=list(state.indices), data_streams=["events"])
        argv = list(
            command(
                SEARCH_SNAPSHOT_PHP,
                str(port),
                "0.5" if fault == "ilm_stuck" else "10",
                "save",
                "null",
            )
        )
        at = argv.index(str(IMAGE))
        argv[at:at] = ["--bind", str(tmp_path) + ":/state/elasticsearch/snapshots"]
        result = subprocess.run(argv, capture_output=True, timeout=15)
        assert state.calls.count(("POST", "/_ilm/stop")) == 1
        writes = [call for call in state.calls if call[0] == "PUT"]
        assert len(writes) == len(set(writes))
        if fault == "none":
            assert result.returncode == 0, result.stderr.decode()
            assert json.loads(result.stdout)["snapshot"] == state.record
            assert len(writes) == 2
        else:
            assert result.returncode == 2, (result.stdout, result.stderr)
            error = json.loads(result.stderr.splitlines()[-1])
            assert (
                not error["attempted_deletions"]
                and not error["attempted_stream_deletions"]
            )
            if fault in ("stop_unconfirmed", "ilm_stuck", "repository_exists"):
                assert not writes
            if fault == "ilm_stuck":
                assert state.calls.count(("GET", "/_ilm/status")) >= 2
        assert not [call for call in state.calls if call[0] == "DELETE"]


@pytest.mark.parametrize(
    "fault",
    ["none", "partial_snapshot", "closed_index", "wrong_repository", "duplicates"],
)
def test_native_restore_preflight_is_readonly(fault: str) -> None:
    with search_server(fault) as (state, port):
        result = subprocess.run(
            command(
                SEARCH_SNAPSHOT_PHP,
                str(port),
                "10",
                "preflight",
                json.dumps(state.record, separators=(",", ":")),
            ),
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == (0 if fault == "none" else 2), result.stderr
        assert all(method == "GET" for method, _ in state.calls)
        assert not state.deleted and not state.restored
        if fault == "none":
            assert json.loads(result.stdout)["operation"] == "preflight"


@pytest.mark.parametrize("fault", ["ilm_running", "foreign_backing"])
def test_restore_preflight_rejects_unready_search_without_mutation(fault: str) -> None:
    with search_server("none") as (state, port):
        if fault == "ilm_running":
            state.ilm = "RUNNING"
        else:
            state.streams = {"events": ["absent"]}
        result = subprocess.run(
            command(
                SEARCH_SNAPSHOT_PHP,
                str(port),
                "10",
                "preflight",
                json.dumps(state.record, separators=(",", ":")),
            ),
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 2
        assert all(method == "GET" for method, _ in state.calls)
        assert not state.deleted and not state.restored


@pytest.mark.parametrize("program", ["database", "search"])
def test_backend_drain_program_syntax(program: str) -> None:
    from lab_generate_skill.sites.shopping_admin.drain_program import (
        DATABASE_DRAIN_PHP,
        SEARCH_DRAIN_PHP,
    )

    selected = DATABASE_DRAIN_PHP if program == "database" else SEARCH_DRAIN_PHP
    result = subprocess.run(
        command("if(false){" + selected + "}"), capture_output=True, timeout=15
    )
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "busy",
        "missing",
        "bad_nodes",
        "missing_tasks",
        "failure",
        "bad_failure",
        "overflow",
    ],
)
def test_backend_search_drain_reply_and_single_read(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    from typing import Any
    from search_http_fixtures import SearchServer
    from lab_generate_skill.sites.shopping_admin.drain_program import SEARCH_DRAIN_PHP

    reply: dict[str, Any] = {"nodes": {}}
    if case == "busy":
        reply = {"nodes": {"original": {"tasks": {"one": {}, "two": {}}}}}
    elif case == "missing":
        reply = {}
    elif case == "bad_nodes":
        reply = {"nodes": False}
    elif case == "missing_tasks":
        reply = {"nodes": {"original": {}}}
    elif case == "failure":
        reply["node_failures"] = [{"reason": "unavailable"}]
    elif case == "bad_failure":
        reply["task_failures"] = False
    elif case == "overflow":
        reply = {"nodes": {"original": {"tasks": {str(i): {} for i in range(4097)}}}}

    def response(self: SearchServer, method: str, target: str) -> tuple[int, Any]:
        self.calls.append((method, target))
        return 200, reply

    monkeypatch.setattr(SearchServer, "response", response)
    with search_server("none") as (state, port):
        result = subprocess.run(
            command(SEARCH_DRAIN_PHP, str(port), "10"), capture_output=True, timeout=15
        )
        assert state.calls == [
            ("GET", "/_tasks?actions=indices:data/write/*,indices:admin/*")
        ]
        if case in ("empty", "busy"):
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == {
                "search_write_tasks": 2 if case == "busy" else 0
            }
        else:
            assert result.returncode == 2, result.stdout
            assert result.stderr and not result.stdout
