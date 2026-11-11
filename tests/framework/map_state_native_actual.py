"""Original PG11 all-table guard and sequence semantics in one tiny private DB."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import traceback
from typing import Any
import pytest
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.adapters.processes.capture import retained_capture
from lab_generate_skill.sites.map.state_guard import MapStateChanged
from lab_generate_skill.sites.map.state_sql import STATE_SQL
from lab_generate_skill.sites.map.state_rules import database_state, fingerprint
from lab_generate_skill.adapters.map_runtime.controls import BoundedMapStartupControls
from map_state_native_fixture import TinyMapNative, SCHEMA
from test_slurm_commands import guard


def test_native_fixture_is_small_explicit_and_state_sql_deadline_intersects() -> None:
    assert len(SCHEMA) < 8192 and SCHEMA.count(b"CREATE TABLE") == 6
    assert b"codex_reset_guard" not in SCHEMA and b"DROP " not in SCHEMA
    assert BoundedMapStartupControls().bind(guard(2), "state_sql").checkpoint() <= 2
    assert BoundedMapStartupControls().bind(guard(120), "state_sql").checkpoint() <= 60


def test_original_pg11_guard_tracks_rollback_sequences_every_write_and_coverage() -> (
    None
):
    root = Path(tempfile.mkdtemp(prefix="lab-map-guard-small-", dir="/tmp"))
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    fixture = TinyMapNative(root)
    primary: BaseException | None = None
    facts: dict[str, Any] = dict(
        engineering_only=True,
        benchmark_database=False,
        registered_worker=False,
        actual_map_website=False,
        actual_actor=False,
        paid_calls=0,
        original_root=str(root),
    )
    try:
        tracker = fixture.initialize(guard(90))
        initial = tracker.install(guard(60))
        database = database_state(initial.database)
        assert (
            database["tables"]
            == database["tracked"]
            == ["deleted", "inserted", "notes", "truncated", "updated", "users"]
        )
        assert database["changed"] == []
        assert database["sequences"] == [["notes_id_seq", 1], ["users_id_seq", 1]]
        assert tracker.require_unchanged(guard()).sha256 == initial.sha256
        fixture.sql(b"BEGIN; UPDATE notes SET body='rolled back'; ROLLBACK;\n", guard())
        assert tracker.require_unchanged(guard()).sha256 == initial.sha256
        facts["rollback_unchanged"] = True
        fixture.sql(b"SELECT nextval('notes_id_seq');\n", guard())
        after_sequence = fixture.sql(STATE_SQL.encode(), guard())
        sequence = database_state(after_sequence)
        assert sequence["changed"] == [] and sequence["sequences"] == [
            ["notes_id_seq", 2],
            ["users_id_seq", 1],
        ]
        with pytest.raises(MapStateChanged):
            tracker.require_unchanged(guard())
        assert tracker.state == "changed" and tracker.initial is initial
        with pytest.raises(InvalidTransition):
            tracker.require_unchanged(guard())
        with pytest.raises(InvalidTransition):
            tracker.install(guard())
        facts["sequence_without_table_write_detected"] = True
        # Following calls are explicit fixture observations, not retries of the
        # poisoned guard or cleared/reused production tracking state.
        fixture.sql(
            b"INSERT INTO inserted VALUES (1); UPDATE updated SET id=2; DELETE FROM deleted; TRUNCATE truncated;\n",
            guard(),
        )
        after_writes = fixture.sql(STATE_SQL.encode(), guard())
        writes = database_state(after_writes)
        assert writes["changed"] == [
            "public.deleted",
            "public.inserted",
            "public.truncated",
            "public.updated",
        ]
        assert fingerprint(initial.persistent, after_writes) != initial.sha256
        facts["all_four_statement_write_kinds_detected"] = True
        fixture.sql(b"CREATE TABLE new_untracked(id integer);\n", guard())
        missing = fixture.sql(STATE_SQL.encode(), guard())
        with pytest.raises(ValueError, match="every public table"):
            database_state(missing)
        fixture.sql(
            b"ALTER TABLE users DISABLE TRIGGER codex_reset_guard_write;\n", guard()
        )
        disabled = fixture.sql(STATE_SQL.encode(), guard())
        raw = json.loads(disabled)
        assert "users" in raw["tables"] and "users" not in raw["tracked"]
        with pytest.raises(ValueError, match="every public table"):
            database_state(disabled)
        facts["new_table_and_disabled_trigger_refused"] = True
        for name, body in (
            ("initial", initial.database),
            ("sequence", after_sequence),
            ("writes", after_writes),
            ("new-table", missing),
            ("disabled-trigger", disabled),
        ):
            (output / ("map-state-native-" + name + ".json")).write_bytes(body)
        facts["initial_fingerprint"] = initial.sha256
        facts["initial_persistent"] = initial.persistent.model_dump(mode="json")
    except BaseException as error:
        primary = error
        (output / "map-state-native-failure.txt").write_text(
            "".join(traceback.format_exception(error))
        )
        capture = retained_capture(error)
        if capture is not None:
            (output / "map-state-native-stdout.bin").write_bytes(capture.stdout)
            (output / "map-state-native-stderr.bin").write_bytes(capture.stderr)
        raise
    finally:
        cleanup: list[BaseException] = []
        services = fixture.services
        if services is not None:
            try:
                if primary is None:
                    quiet = services.quiesce(guard(30))
                    facts["native_quiescence"] = quiet.model_dump(mode="json")
            except BaseException as error:
                cleanup.append(error)
            try:
                held = services.namespaces.get("app_postgres")
                if (
                    (primary is not None or cleanup)
                    and held is not None
                    and held.stopped is None
                ):
                    facts["forced_namespace_cleanup"] = services.stop_namespace(
                        "app_postgres", guard(30)
                    ).model_dump(mode="json")
            except BaseException as error:
                cleanup.append(error)
            try:
                exits = services.stop(guard(30))
                facts["original_service_exits"] = [
                    e.model_dump(mode="json") for e in exits
                ]
                assert all(e.state == "reaped" for e in exits)
            except BaseException as error:
                cleanup.append(error)
        log = Path(fixture.spec.inputs.files.log_root) / "app_postgres.log"
        if log.exists():
            (output / "map-state-native-postgres.log").write_bytes(log.read_bytes())
        facts["cleanup_errors"] = [repr(e) for e in cleanup]
        facts["passed"] = primary is None and not cleanup
        facts["root_retained"] = not facts["passed"]
        if facts["passed"]:
            shutil.rmtree(root)
        (output / "map-state-native-result.json").write_text(
            json.dumps(facts, indent=2) + "\n"
        )
        if cleanup:
            raise BaseExceptionGroup(
                "Native Map state fixture primary and cleanup errors",
                ([primary] if primary is not None else []) + cleanup,
            ) from None
