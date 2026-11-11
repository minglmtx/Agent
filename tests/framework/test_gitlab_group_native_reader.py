"""Fixed port transport, incomplete/failed reads and captured-fact composition."""

import json
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.bootstrap.gitlab_group_state import load_group_state
from lab_generate_skill.domain.errors import OperationStopped, EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.group_native_reader import GitlabGroupNativeReader
from lab_generate_skill.sites.gitlab.group_sql_capture import GROUP_CAPTURE
from lab_generate_skill.sites.gitlab.tasks.group_rules import decide_group
from lab_generate_skill.domain.evidence_io import MAX_OBJECT_BYTES
from gitlab_native_fixtures import spec as services
from gitlab_group_fixtures import native_state, selected_spec, page, ORIGIN
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


class Commands:
    def __init__(self) -> None:
        self.raw = native_state().model_dump_json().encode()
        self.calls: list[tuple[tuple[str, ...], bytes]] = []
        self.error: BaseException | None = None

    def run_input(
        self, argv: tuple[str, ...], data: bytes, control: OperationControl
    ) -> bytes:
        control.checkpoint()
        self.calls.append((argv, data))
        if self.error is not None:
            raise self.error
        return self.raw


def test_capture_complete_facts_then_original_decision_and_independent_readback(
    node_path: Path,
) -> None:
    commands, spec = Commands(), selected_spec()
    reader = GitlabGroupNativeReader(services(node_path), commands, load_group_state)
    before = reader.capture(spec, "native-user", guard())
    before_bytes = reader.captured_raw
    commands.raw = native_state(inserted=True).model_dump_json().encode()
    after = reader.capture(spec, "native-user", guard())
    assert reader.captured_raw == commands.raw and before_bytes is not None
    assert len(commands.calls) == 2
    for argv, data in commands.calls:
        assert argv[-2:] == ("-e", GROUP_CAPTURE)
        assert b"Development Team" not in data and "native-user" not in " ".join(argv)
        assert json.loads(data) == dict(
            task=spec.task.model_dump(mode="json"),
            username="native-user",
            with_settings=True,
        )
    decision = decide_group(
        spec,
        before,
        after,
        page(),
        site_origin=ORIGIN,
        selected_projects_unchanged=True,
    )
    # These are synthetic selected-project facts, not a native protection receipt.
    independent = decide_group(
        spec,
        load_group_state(before_bytes, spec),
        load_group_state(commands.raw, spec),
        page(),
        site_origin=ORIGIN,
        selected_projects_unchanged=True,
    )
    assert decision == independent and decision.status == "success"
    assert len(commands.calls) == 2  # readback and decision do not dispatch SQL


@pytest.mark.parametrize(
    "value",
    [None, 1, True, [], {}, "", "x" * 256, "a\nb", "x' OR true", "a/b", "用户名"],
)
def test_bad_username_refused_before_transport(node_path: Path, value: object) -> None:
    commands = Commands()
    with pytest.raises(ValueError):
        GitlabGroupNativeReader(
            services(node_path), commands, load_group_state
        ).capture(selected_spec(), cast(str, value), guard())
    assert commands.calls == []


@pytest.mark.parametrize(
    "error",
    [
        OSError("SQL partial output"),
        OperationStopped("CANCELLED", "group-read"),
        ExceptionGroup("native and close", [OSError("read"), RuntimeError("close")]),
    ],
)
def test_original_error_and_cleanup_retained_without_automatic_reinvocation(
    node_path: Path, error: BaseException
) -> None:
    commands = Commands()
    reader = GitlabGroupNativeReader(services(node_path), commands, load_group_state)
    reader.capture(selected_spec(), "native-user", guard())
    commands.error = error
    with pytest.raises(type(error)) as caught:
        reader.capture(selected_spec(), "native-user", guard())
    assert (
        caught.value is error
        and len(commands.calls) == 2
        and reader.captured_raw is None
    )


@pytest.mark.parametrize(
    "fault", ["foreign-user", "foreign-task", "partial-json", "empty", "over-limit"]
)
def test_incomplete_or_foreign_capture_keeps_only_this_known_raw(
    node_path: Path, fault: str
) -> None:
    commands = Commands()
    data = native_state().model_dump(mode="json")
    if fault == "foreign-user":
        data["user"]["username"] = "foreign"
    elif fault == "foreign-task":
        data["task"]["source_task_id"] = "foreign"
    commands.raw = json.dumps(data).encode()
    if fault == "partial-json":
        commands.raw = b'{"task":'
    elif fault == "empty":
        commands.raw = b""
    elif fault == "over-limit":
        commands.raw = b" " * (MAX_OBJECT_BYTES + 1)
    reader = GitlabGroupNativeReader(services(node_path), commands, load_group_state)
    with pytest.raises((ValueError, EvidenceIntegrityError)):
        reader.capture(selected_spec(), "native-user", guard())
    assert len(commands.calls) == 1
    assert reader.captured_raw == (
        None if fault in ("empty", "over-limit") else commands.raw
    )


class StopAt:
    def __init__(self, checkpoint: int) -> None:
        self.stop, self.calls = checkpoint, 0
        self.error = OperationStopped("CANCELLED", "original-group-read")

    def checkpoint(self) -> float:
        self.calls += 1
        if self.calls == self.stop:
            raise self.error
        return 1.0

    def wait(self, seconds: float) -> None:
        raise AssertionError("Native reader must not wait or retry")


@pytest.mark.parametrize("stop", [1, 2, 3])
def test_cancel_before_effect_or_after_known_return_preserves_exact_boundary(
    node_path: Path, stop: int
) -> None:
    commands, control = Commands(), StopAt(stop)
    reader = GitlabGroupNativeReader(services(node_path), commands, load_group_state)
    with pytest.raises(OperationStopped) as caught:
        reader.capture(selected_spec(), "native-user", control)
    assert caught.value is control.error
    assert len(commands.calls) == (1 if stop == 3 else 0)
    assert reader.captured_raw == (commands.raw if stop == 3 else None)
