"""Actual original Ruby/psql/PG on synthetic rows, never an Actor or source run."""

import base64
import json
import os
from pathlib import Path
import shutil
import tempfile
import traceback
import pytest
from lab_generate_skill.adapters.processes.capture import (
    CommandFailure,
    retained_capture,
)
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.sites.gitlab.tasks.group_capture import GroupCapturedFacts
from lab_generate_skill.sites.gitlab.tasks.group_rules import (
    decide_group,
    validate_group_initial,
)
from lab_generate_skill.sites.gitlab.project_copy import PROJECT_ARGV
from gitlab_group_native_fixture import TinyGroup
from gitlab_group_fixtures import selected_spec, page, ORIGIN
from test_slurm_commands import guard


def test_actual_group_native_original_replies_guard_empty_and_partial_failure() -> None:
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    root = Path(tempfile.mkdtemp(prefix="lab-gitlab-group-tiny-", dir="/tmp"))
    fixture = TinyGroup(root)
    primary: BaseException | None = None
    proof: dict[str, object] = {
        "engineering_only": True,
        "benchmark_database": False,
        "registered_site_worker": False,
        "actual_Actor": False,
        "paid_calls": 0,
        "production_image_staging": False,
        "fixture_mount_prefix_adapter_only": True,
    }

    def capture(label: str) -> GroupCapturedFacts:
        facts = fixture.reader.capture(selected_spec(), "native-user", guard(60))
        raw = fixture.reader.captured_raw
        assert raw is not None
        calls = len(fixture.inputs.calls)
        independent = load_group_capture(raw, selected_spec())
        assert independent == facts and len(fixture.inputs.calls) == calls
        (output / ("group-tiny-" + label + ".json")).write_bytes(raw)
        assert fixture.inputs.calls[-1][0][-len(PROJECT_ARGV) :] == PROJECT_ARGV
        return facts

    try:
        fixture.initialize(guard(90))
        before = capture("before")
        validate_group_initial(selected_spec(), before.state)
        expected = b'1,10,"Original, project",original\n2,11,"Line\nbreak",second\n'
        assert before.project_copy == expected
        assert len(before.state.groups) == len(before.state.members) == 1
        assert before.state.settings is not None and len(before.state.settings) == 1
        initial = decide_group(
            selected_spec(),
            before.state,
            before.state,
            page(),
            site_origin=ORIGIN,
            selected_projects_unchanged=True,
        )
        assert initial.status == "failure" and initial.reward == 0
        fixture.add_selected_group(guard())
        saved = capture("saved")
        result = decide_group(
            selected_spec(),
            before.state,
            saved.state,
            page(),
            site_origin=ORIGIN,
            selected_projects_unchanged=before.project_copy == saved.project_copy,
        )
        assert (
            result.status == "success"
            and result.reward == 1
            and not result.state_change_requires_review
        )
        fixture.native.sql(
            b"UPDATE projects SET name='Changed project' WHERE id=1;\n", guard()
        )
        changed = capture("project-change")
        result = decide_group(
            selected_spec(),
            before.state,
            changed.state,
            page(),
            site_origin=ORIGIN,
            selected_projects_unchanged=before.project_copy == changed.project_copy,
        )
        assert (
            result.status == "unknown"
            and result.reward is None
            and result.state_change_requires_review
        )
        fixture.native.sql(
            b"UPDATE namespace_settings SET setup_for_company=false WHERE namespace_id=20;\n",
            guard(),
        )
        wrong = capture("goal-and-project-change")
        result = decide_group(
            selected_spec(),
            before.state,
            wrong.state,
            page(),
            site_origin=ORIGIN,
            selected_projects_unchanged=False,
        )
        assert (
            result.status == "failure"
            and result.reward == 0
            and result.state_change_requires_review
        )
        fixture.native.sql(b"DELETE FROM projects;\n", guard())
        empty = capture("empty-projects")
        assert empty.project_copy == b""
        fixture.native.sql(b"DROP TABLE projects;\n", guard())
        calls = len(fixture.inputs.calls)
        with pytest.raises(CommandFailure) as failed:
            fixture.reader.capture(selected_spec(), "native-user", guard(60))
        assert (
            len(fixture.inputs.calls) == calls + 2
            and fixture.reader.captured_raw is None
        )
        assert (
            fixture.reader.groups.captured_raw is not None
            and fixture.reader.projects.captured_raw is None
        )
        assert (
            fixture.reader.last_failure is failed.value
            and fixture.reader.failed_stage == "projects"
        )
        partial = fixture.reader.groups.captured_raw
        (output / "group-tiny-partial-completed-native.json").write_bytes(partial)
        failure_capture = retained_capture(failed.value)
        assert failure_capture is not None and failure_capture.returncode != 0
        (output / "group-tiny-expected-copy-error.stdout.bin").write_bytes(
            failure_capture.stdout
        )
        (output / "group-tiny-expected-copy-error.stderr.bin").write_bytes(
            failure_capture.stderr
        )
        proof.update(
            native_group_rows=len(before.state.groups),
            native_members=len(before.state.members),
            native_settings=len(before.state.settings),
            original_csv_base64=base64.b64encode(expected).decode(),
            complete_original_replies_independently_decoded=True,
            non_group_rows_excluded=True,
            selected_group_saved=True,
            protected_project_change_unknown=True,
            goal_failure_and_project_change_remains_failure_with_review=True,
            empty_csv_valid=True,
            expected_partial_copy_error_without_retry=True,
            original_native_read_calls=len(fixture.inputs.calls),
            full_site_restore=False,
        )
    except BaseException as error:
        primary = error
        (output / "group-tiny-failure.txt").write_text(
            "".join(traceback.format_exception(error))
        )
        captured = retained_capture(error)
        if captured is not None:
            (output / "group-tiny-failure.stdout.bin").write_bytes(captured.stdout)
            (output / "group-tiny-failure.stderr.bin").write_bytes(captured.stderr)
        (output / "group-tiny-retained-root.txt").write_text(str(root) + "\n")
        raise
    finally:
        cleanup_errors: list[BaseException] = []
        quiet = None
        try:
            if primary is None:
                quiet = fixture.native.services.quiesce(guard(20))
        except BaseException as error:
            cleanup_errors.append(error)
        try:
            held = fixture.native.services.namespaces.get("postgres")
            if (
                (primary is not None or cleanup_errors)
                and held is not None
                and held.stopped is None
            ):
                fixture.native.services.stop_namespace("postgres", guard(20))
        except BaseException as error:
            cleanup_errors.append(error)
        try:
            exits = fixture.native.services.stop(guard(20))
            assert all(e.state == "reaped" for e in exits)
        except BaseException as error:
            cleanup_errors.append(error)
        if cleanup_errors:
            raise BaseExceptionGroup(
                "Tiny Group primary and cleanup failures",
                ([primary] if primary is not None else []) + cleanup_errors,
            ) from None
    proof.update(
        native_quiescence=None if quiet is None else quiet.model_dump(mode="json"),
        original_service_exits=[e.model_dump(mode="json") for e in exits],
    )
    (output / "group-tiny-native-proof.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    shutil.rmtree(root)
