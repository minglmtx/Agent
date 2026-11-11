"""Complete paired raw sources and strict readonly decoding, never SQL replay."""

import base64
import json
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.gitlab.tasks.group_capture import GroupCapturePayload
from lab_generate_skill.sites.gitlab.project_copy import PROJECT_COPY
from gitlab_group_lifecycle_fixtures import case, PROJECTS
from gitlab_group_fixtures import native_state, selected_spec
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def payload(projects: bytes = PROJECTS) -> GroupCapturePayload:
    return GroupCapturePayload(
        task=selected_spec().task,
        project_query=PROJECT_COPY,
        group_reply_base64=base64.b64encode(
            native_state().model_dump_json().encode()
        ).decode(),
        project_copy_base64=base64.b64encode(projects).decode(),
    )


@pytest.mark.parametrize("projects", [b"", PROJECTS])
def test_source_envelope_keeps_all_original_bytes_and_empty_is_not_missing(
    projects: bytes,
) -> None:
    raw = payload(projects).model_dump_json().encode()
    result = load_group_capture(raw, selected_spec())
    assert result.state == native_state() and result.project_copy == projects
    assert result.group_reply == native_state().model_dump_json().encode()
    assert load_group_capture(raw, selected_spec()) == result


@pytest.mark.parametrize(
    "fault",
    [
        "missing-copy",
        "null-copy",
        "wrong-type",
        "bad-base64",
        "noncanonical",
        "inner-duplicate",
        "inner-missing-version",
        "foreign",
        "query",
        "old",
        "outer-duplicate",
    ],
)
def test_missing_foreign_ambiguous_or_relabelled_sources_refused(fault: str) -> None:
    data = payload().model_dump(mode="json")
    if fault == "missing-copy":
        data.pop("project_copy_base64")
    elif fault == "null-copy":
        data["project_copy_base64"] = None
    elif fault == "wrong-type":
        data["group_reply_base64"] = 1
    elif fault == "bad-base64":
        data["project_copy_base64"] = "!"
    elif fault == "noncanonical":
        data["project_copy_base64"] += "="
    elif fault.startswith("inner-"):
        inner = native_state().model_dump_json().encode()
        if fault == "inner-duplicate":
            inner = b'{"user":null,' + inner[1:]
        else:
            obj = json.loads(inner)
            obj.pop("schema_version")
            inner = json.dumps(obj).encode()
        data["group_reply_base64"] = base64.b64encode(inner).decode()
    elif fault == "foreign":
        data["task"]["source_task_id"] = "other"
    elif fault == "query":
        data["project_query"] = "SELECT true"
    elif fault == "old":
        data["schema_version"] = "gitlab-group-capture-payload/0"
    raw = json.dumps(data, separators=(",", ":")).encode()
    if fault == "outer-duplicate":
        raw = b'{"task":null,' + raw[1:]
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        load_group_capture(raw, selected_spec())


def test_fixed_composite_capture_has_two_reads_and_no_readback_dispatch(
    node_path: Path,
) -> None:
    c = case(node_path)
    reader = c.task.reader
    value = reader.capture(selected_spec(), "native-user", guard())
    assert value.project_copy == PROJECTS and len(c.sql.calls) == 2
    assert reader.captured_raw is not None
    assert load_group_capture(reader.captured_raw, selected_spec()) == value
    assert len(c.sql.calls) == 2
    c.task.instance.stop(guard())


def test_failed_later_read_cannot_reuse_previous_project_bytes(node_path: Path) -> None:
    c = case(node_path)
    reader = c.task.group_reader
    reader.capture(selected_spec(), "native-user", guard())
    original = OSError("later group SELECT failed")
    c.sql.error, c.sql.fail_part = original, "groups"
    with pytest.raises(OSError) as caught:
        reader.capture(selected_spec(), "native-user", guard())
    assert caught.value is original and reader.last_failure is original
    assert (
        reader.captured_raw is None
        and reader.groups.captured_raw is None
        and reader.projects.captured_raw is None
    )
    assert len(c.sql.calls) == 3
    c.task.instance.stop(guard())
