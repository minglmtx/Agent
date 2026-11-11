"""Current native/media composition with fake database, no PG or website."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.sites.reddit.native_reader import DatabaseEnvelope
from lab_generate_skill.sites.reddit.native_schema import NativeMedia
from reddit_native_reader_fixtures import case
from reddit_image_state_fixtures import reference_data, posted_data
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_reference_and_capture_use_original_task_small_selector_and_separate_media(
    node_path: Path,
) -> None:
    reader, commands, media, spec, inputs, baseline = case(node_path)
    before = reader.reference(spec, "native-user", guard(5))
    assert (
        before.account.username == "native-user"
        and before.target_forum.name == "EarthPorn"
    )
    media.value = NativeMedia.model_validate_json(
        json.dumps(posted_data()["native_media"])
    )
    after = reader.capture(spec, "native-user", baseline, guard(5))
    assert after.added_posts[0]["id"] == 3 and reader.last_result == after
    assert len(commands.calls) == 2
    for argv, data in commands.calls:
        assert len(data) <= 8192 and "ranges" not in json.loads(data)
        assert json.loads(data)["task"] == spec.task.model_dump(mode="json")
        assert argv[-1] == str(reader.services.ports.database)
    assert (
        reader.services.native_input_root + ":/native-input:ro"
        not in commands.calls[0][0]
    )
    assert (
        reader.services.native_input_root + ":/native-input:ro" in commands.calls[1][0]
    )
    inputs.verify(baseline, guard(5))


@pytest.mark.parametrize(
    "kind",
    ["task", "mode", "reference", "missing-capture", "json", "empty", "foreign-file"],
)
def test_wrong_native_result_or_input_is_not_promoted(
    node_path: Path, kind: str
) -> None:
    reader, commands, _, spec, _, baseline = case(node_path)
    data = reference_data()
    capture = data.pop("capture")
    capture.pop("native_media")
    envelope = dict(
        schema_version="reddit-native-database-capture/1",
        task=spec.task.model_dump(mode="json"),
        mode="reference",
        reference=data,
        capture=capture,
    )
    if kind == "task":
        envelope["task"]["source_task_id"] = "different-source"
    elif kind == "mode":
        envelope["mode"] = "capture"
    elif kind == "reference":
        envelope["reference"] = None
    elif kind == "missing-capture":
        del envelope["capture"]["complete13"]
    if kind in ("json", "empty"):
        commands.reply = b"{" if kind == "json" else b""
    else:
        commands.reply = json.dumps(envelope).encode()
    with pytest.raises((ValueError, EvidenceIntegrityError, OwnershipConflict)):
        if kind == "foreign-file":
            reader.capture(
                spec,
                "native-user",
                baseline.model_copy(
                    update={
                        "task": spec.task.model_copy(update={"source_task_id": "other"})
                    }
                ),
                guard(5),
            )
        else:
            reader.reference(spec, "native-user", guard(5))
    assert reader.last_result is None
    if kind == "foreign-file":
        assert commands.calls == []


def test_media_failure_keeps_known_database_and_does_not_repeat_native_command(
    node_path: Path,
) -> None:
    reader, commands, media, spec, _, _ = case(node_path)
    media.failure = OSError("original media unavailable")
    with pytest.raises(OSError, match="original media unavailable"):
        reader.reference(spec, "native-user", guard(5))
    assert (
        len(commands.calls) == 1
        and reader.last_database is not None
        and reader.last_result is None
    )


def test_final_cancellation_preserves_complete_original_result(node_path: Path) -> None:
    reader, commands, _, spec, _, _ = case(node_path)

    class CancelAfter:
        def checkpoint(self) -> float:
            if reader.last_result is not None:
                raise TimeoutError("late cancellation")
            return 5

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(TimeoutError, match="late cancellation"):
        reader.reference(spec, "native-user", CancelAfter())
    assert (
        reader.last_result is not None
        and reader.last_database is not None
        and len(commands.calls) == 1
    )
