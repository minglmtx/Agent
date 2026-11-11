"""Small native ABC before expensive selected whole-site integration."""

import hashlib
import json
import os
import tempfile
import traceback
import shutil
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_ssh_state import load_ssh_key_state
from lab_generate_skill.sites.gitlab.tasks.ssh_key_state import (
    PROTECTED_TABLES,
    SshKeyNativeState,
)
from lab_generate_skill.sites.gitlab.tasks.ssh_key_rules import preserved
from gitlab_ssh_native_fixture import TinyNative, schema_sql, literal, PG
from gitlab_ssh_state_fixtures import selected_spec
from test_slurm_commands import guard


def test_tiny_fixture_schema_preflight() -> None:
    sql = schema_sql().decode()
    assert sql.count("CREATE TABLE") == 17
    assert all(('CREATE TABLE "' + table + '"') in sql for table in PROTECTED_TABLES)
    assert (
        "native-user" in sql and "other-user" in sql and "Original unrelated key" in sql
    )
    assert "DROP " not in sql and "UPDATE " not in sql
    assert (
        literal("a'b") == "'a''b'"
        and literal(True) == "true"
        and literal(None) == "NULL"
    )
    bad_values: tuple[object, ...] = ([], {}, 1.5, b"", "a\0b")
    for bad in bad_values:
        with pytest.raises(ValueError):
            literal(bad)


def test_complete_native_sql_refs_auth_mask_and_failure_boundaries() -> None:
    node_path = Path(tempfile.mkdtemp(prefix="lab-gitlab-ssh-small-", dir="/tmp"))
    fixture = TinyNative(node_path)
    initial: SshKeyNativeState | None = None
    after: SshKeyNativeState | None = None
    primary: BaseException | None = None
    try:
        fixture.initialize(guard(90))
        initial = load_ssh_key_state(fixture.capture(guard(60)), selected_spec())
        assert initial.users.row_count == 2 and initial.keys.row_count == 1
        assert set(initial.guard) == set(PROTECTED_TABLES)
        assert len(initial.refs.repositories) == 3
        assert (
            sum(repo.head is None for repo in initial.refs.repositories.values()) == 2
        )
        fixture.sql(
            b"UPDATE users SET sign_in_count=1,updated_at='changed' WHERE id=1;\n",
            guard(),
        )
        after = load_ssh_key_state(fixture.capture(guard(60)), selected_spec())
        assert initial.guard == after.guard and preserved(initial, after)
        fixture.sql(b"UPDATE users SET sign_in_count=2 WHERE id=2;\n", guard())
        unrelated = load_ssh_key_state(fixture.capture(guard(60)), selected_spec())
        assert initial.guard["users"] != unrelated.guard["users"]
        assert not preserved(initial, unrelated)
        # An explicitly read-only session must never accept a write SELECT.
        from lab_generate_skill.sites.gitlab.ssh_sql_session import SQL_SESSION
        from lab_generate_skill.sites.gitlab.service_commands import RUBY
        from lab_generate_skill.adapters.processes.capture import CommandFailure

        mode = fixture.command(
            (
                RUBY,
                "-e",
                SQL_SESSION
                + "\ndb=LabGitlabSsh::SqlSession.new\nbegin; puts JSON.generate(db.select(\"SELECT current_setting('transaction_read_only') AS mode,current_setting('transaction_isolation') AS isolation\")); ensure; db.finish($!); end\n",
            ),
            guard(10),
        )
        assert json.loads(mode) == [dict(mode="on", isolation="repeatable read")]

        with pytest.raises(CommandFailure):
            fixture.command(
                (
                    RUBY,
                    "-e",
                    SQL_SESSION
                    + "\ndb=LabGitlabSsh::SqlSession.new\nbegin; db.select('SELECT 1; DELETE FROM users'); ensure; db.finish($!); end\n",
                ),
                guard(10),
            )
        assert b"2" == fixture.sql(b"SELECT COUNT(*) FROM users;\n", guard()).strip()
    except BaseException as error:
        primary = error
        from lab_generate_skill.adapters.processes.capture import retained_capture

        output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        (output / "gitlab-ssh-tiny-failure.txt").write_text(
            "".join(traceback.format_exception(error))
        )
        capture = retained_capture(error)
        if capture is not None:
            (output / "gitlab-ssh-tiny-stdout.bin").write_bytes(capture.stdout)
            (output / "gitlab-ssh-tiny-stderr.bin").write_bytes(capture.stderr)
        pglog = node_path / "logs/postgres.log"
        if pglog.exists():
            (output / "gitlab-ssh-tiny-postgres.log").write_bytes(pglog.read_bytes())
        (output / "gitlab-ssh-tiny-retained-root.txt").write_text(str(node_path) + "\n")
        raise
    finally:
        cleanup_errors: list[BaseException] = []
        quiet = None
        try:
            if primary is None:
                quiet = fixture.services.quiesce(guard(20))
        except BaseException as cleanup:
            cleanup_errors.append(cleanup)
        try:
            held = fixture.services.namespaces.get("postgres")
            if (
                (primary is not None or cleanup_errors)
                and held is not None
                and held.stopped is None
            ):
                fixture.services.stop_namespace("postgres", guard(20))
        except BaseException as cleanup:
            cleanup_errors.append(cleanup)
        try:
            exits = fixture.services.stop(guard(20))
            assert all(e.state == "reaped" for e in exits)
        except BaseException as cleanup:
            cleanup_errors.append(cleanup)
        if cleanup_errors:
            raise BaseExceptionGroup(
                "Tiny native primary and cleanup failures",
                ([primary] if primary is not None else []) + cleanup_errors,
            ) from None
    assert initial is not None and after is not None
    proof = dict(
        engineering_only=True,
        registered_site_worker=False,
        production_image_staging=False,
        benchmark_database=False,
        actual_actor=False,
        paid_calls=0,
        complete_users=2,
        complete_keys=1,
        protected_tables=16,
        repositories=3,
        original_auth_mask_preserved=True,
        unrelated_auth_change_detected=True,
        read_only_select_write_refused=True,
        native_quiescence=quiet.model_dump(mode="json") if quiet is not None else None,
        original_capture_sha256=hashlib.sha256(
            initial.model_dump_json().encode()
        ).hexdigest(),
        original_service_exits=[e.model_dump(mode="json") for e in exits],
    )
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "gitlab-ssh-tiny-native.json"
    ).write_text(json.dumps(proof, indent=2) + "\n")
    shutil.rmtree(node_path)
