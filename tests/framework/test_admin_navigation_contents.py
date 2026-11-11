"""Actual PHP readers, semantic content distinctions, and failed native save.

No original website, Actor, source claim or execution permission is involved.
"""

from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.sites.shopping_admin.tasks.navigation_contents import (
    NavigationContentsReply,
    measure_navigation_contents,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_contents_program import (
    NAVIGATION_CONTENTS_PHP,
)
from admin_navigation_contents_fixtures import measured_server, run_measurement, SQL
from admin_navigation_fixtures import case, capture, request
from test_admin_navigation_input import contracts as contracts
from test_admin_search_http import command
from test_slurm_commands import guard
import subprocess

from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from admin_navigation_fixtures import Commands


class ReturnedCancellation:
    def __init__(self) -> None:
        self.original = guard()
        self.returned = False

    def checkpoint(self) -> float:
        if self.returned:
            raise OperationStopped("CANCELLED", "navigation-contents")
        return self.original.checkpoint()

    def wait(self, seconds: float) -> None:
        self.checkpoint()
        self.original.wait(seconds)


@pytest.mark.parametrize("fault", ["cancel_after", "cancel_before", "malformed"])
def test_obtained_measurement_retained_before_post_return_cancellation(
    tmp_path: Path, contracts: Any, fault: str
) -> None:
    worker, _ = case(tmp_path)
    capture(worker, contracts)
    assert worker.snapshot is not None
    control = ReturnedCancellation()

    class Reply(Commands):
        def run(self, argv: tuple[str, ...], actual: OperationControl) -> bytes:
            raw = super().run(argv, actual)
            if fault == "cancel_after":
                control.returned = True
            return b"{}" if fault == "malformed" else raw

    commands = Reply()
    if fault == "cancel_before":
        control.returned = True
    with pytest.raises((OperationStopped, ValueError)) as caught:
        measure_navigation_contents(worker.snapshot.state, commands, control)
    if fault == "cancel_before":
        assert not commands.calls
    else:
        raw = getattr(caught.value, "admin_navigation_contents_raw_reply")
        assert raw
        obtained = getattr(caught.value, "admin_navigation_contents")
        assert (obtained is not None) == (fault == "cancel_after")
        if obtained is not None:
            obtained.require_snapshot(worker.snapshot.state)


def test_program_syntax_with_pinned_php() -> None:
    p = subprocess.run(
        command("if(false){" + NAVIGATION_CONTENTS_PHP + "}"),
        capture_output=True,
        timeout=15,
    )
    assert p.returncode == 0, p.stderr.decode()


def test_actual_contents_equal_across_runtime_identity_dump_time_and_document_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with measured_server(monkeypatch) as (left, port):
        first = run_measurement(tmp_path / "first", port, left.record)
        assert first.returncode == 0, first.stderr.decode()
        one = NavigationContentsReply.model_validate_json(first.stdout)
    with measured_server(monkeypatch, identity="independent") as (right, port):
        second = run_measurement(
            tmp_path / "second",
            port,
            right.record,
            sql=SQL.replace(b"2026-11-02 20:00:00", b"2026-11-03 21:01:02")
            + b"-- Dump completed on 2026-11-03 21:01:02\n",
        )
        assert second.returncode == 0, second.stderr.decode()
        two = NavigationContentsReply.model_validate_json(second.stdout)
    assert one.database_raw_sha256 != two.database_raw_sha256
    assert one.model_dump(exclude={"database_raw_sha256"}) == two.model_dump(
        exclude={"database_raw_sha256"}
    )


@pytest.mark.parametrize(
    "fault", ["document", "metadata", "sql", "empty_object", "other_timestamp"]
)
def test_actual_content_differences_are_not_normalized_away(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with measured_server(monkeypatch) as (state, port):
        first = run_measurement(tmp_path / "first", port, state.record)
        assert first.returncode == 0, first.stderr.decode()
    sql = None
    if fault == "sql":
        sql = (
            SQL.replace(b"unchanged", b"changed")
            + b"-- Dump completed on 2026-11-02 20:00:00\n"
        )
    if fault == "other_timestamp":
        sql = (
            SQL.replace(b"2026-01-01 00:00:00", b"2026-01-02 00:00:00")
            + b"-- Dump completed on 2026-11-02 20:00:00\n"
        )
    with measured_server(monkeypatch, fault=fault) as (state, port):
        second = run_measurement(tmp_path / "second", port, state.record, sql=sql)
        assert second.returncode == 0, second.stderr.decode()
    a, b = (
        NavigationContentsReply.model_validate_json(p.stdout) for p in (first, second)
    )
    assert a.model_dump(exclude={"database_raw_sha256"}) != b.model_dump(
        exclude={"database_raw_sha256"}
    )


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_port",
        "wrong_host",
        "wrong_origin",
        "wrong_timestamp",
        "no_automatic_timestamp",
        "wrong_column",
        "missing_schema",
        "missing_startup_rows",
        "duplicate_startup_row",
        "unterminated_literal",
    ],
)
def test_startup_projection_requires_actual_schema_values_and_complete_original_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    sql = SQL
    if fault == "wrong_port":
        sql = sql.replace(b"'__PORT__'", b"'0'")
    elif fault == "wrong_host":
        sql = sql.replace(b"'127.0.0.1'", b"'localhost'")
    elif fault == "wrong_origin":
        sql = sql.replace(b"http://127.0.0.1:12001/", b"http://127.0.0.1:12002/")
    elif fault == "wrong_timestamp":
        sql = sql.replace(b"2026-11-02 20:00:00", b"yesterday")
    elif fault == "no_automatic_timestamp":
        sql = sql.replace(b" ON UPDATE CURRENT_TIMESTAMP", b"")
    elif fault == "wrong_column":
        sql = sql.replace(b"`updated_at`", b"`business_time`")
    elif fault == "missing_schema":
        sql = sql.replace(
            b"CREATE TABLE `core_config_data`", b"CREATE TABLE `other_table`"
        )
    elif fault == "missing_startup_rows":
        sql = sql.replace(
            b"catalog/search/opensearch_server_port", b"unrecognized/path"
        )
    elif fault == "unterminated_literal":
        prefix = b"INSERT INTO `core_config_data` VALUES "
        before, rows = sql.split(prefix, 1)
        sql = before + prefix + rows.replace(b"'default'", b"'default", 1)
    else:
        prefix = b"INSERT INTO `core_config_data` VALUES "
        before, after = sql.split(prefix, 1)
        body, remainder = after.split(b";\n", 1)
        row = body[: body.index(b"),") + 1]
        sql = before + prefix + body + b"," + row + b";\n" + remainder
    with measured_server(monkeypatch) as (state, port):
        result = run_measurement(
            tmp_path,
            port,
            state.record,
            sql=sql + b"-- Dump completed on 2026-11-02 20:00:00\n",
        )
        assert result.returncode == 2 and not result.stdout and result.stderr
        assert not state.calls  # Invalid native baseline never reaches live search.


@pytest.mark.parametrize(
    "fault",
    [
        "snapshot",
        "writer",
        "concurrent_metadata",
        "timeout",
        "shard",
        "count",
        "inexact_count",
        "missing_source",
        "close",
        "raw_pin",
        "footer",
        "empty",
    ],
)
def test_incomplete_or_mismatched_measurement_fails_and_closes_only_original_scroll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with measured_server(monkeypatch, fault=fault) as (state, port):
        p = run_measurement(
            tmp_path,
            port,
            state.record,
            wrong_pin=fault == "raw_pin",
            sql=SQL if fault == "footer" else b"" if fault == "empty" else None,
        )
        assert p.returncode == 2 and not p.stdout, (p.returncode, p.stdout, p.stderr)
        assert p.stderr
        assert all(
            method != "DELETE" or path == "/_search/scroll"
            for method, path in state.calls
        )
        if fault in ("timeout", "shard", "count", "inexact_count", "missing_source"):
            assert state.calls.count(("DELETE", "/_search/scroll")) == 1


def test_producer_pins_full_snapshot_and_legacy_cannot_invent_contents(
    tmp_path: Path, contracts: Any
) -> None:
    worker, commands = case(tmp_path)
    capture(worker, contracts)
    assert worker.snapshot is not None and worker.snapshot.contents is not None
    contents = worker.snapshot.contents
    contents.require_snapshot(worker.snapshot.state)
    changed = worker.snapshot.state.model_copy(
        update={
            "database": worker.snapshot.state.database.model_copy(
                update={"sha256": "0" * 64}
            )
        }
    )
    with pytest.raises(ValueError, match="original measured snapshot"):
        contents.require_snapshot(changed)
    bad = contents.model_dump()
    bad["artifacts"] = ()
    with pytest.raises(ValidationError):
        type(contents).model_validate(bad)
    assert (
        commands.calls[-1][commands.calls[-1].index(NAVIGATION_CONTENTS_PHP) + 3]
        == worker.snapshot.state.database.sha256
    )


def test_partial_contents_failure_retains_actual_state_and_quarantines_no_retry(
    tmp_path: Path, contracts: Any
) -> None:
    worker, commands = case(tmp_path)
    commands.fail = "navigation:contents"
    with pytest.raises(OSError, match="failed-navigation:contents") as caught:
        worker.execute_task(request(contracts), control=guard())
    assert (
        getattr(caught.value, "admin_navigation_state_snapshot")
        is worker.authority.snapshot
    )
    assert worker.snapshot is None and worker.phase == "quarantined"
    count = len(commands.calls)
    with pytest.raises(Exception, match="quarantined"):
        worker.execute_task(
            request(contracts, operation_id="repeated-snapshot"), control=guard()
        )
    assert len(commands.calls) == count
