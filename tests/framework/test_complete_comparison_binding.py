"""Bind the final strategy to complete prior exports; no tokenizer/model repeat."""

import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.actor_projection import build_actor_projection
from lab_generate_skill.domain.actor_projection import MapRailsAddressableProjection
from lab_generate_skill.domain.teacher_input import native_evidence
from lab_generate_skill.teacher.field_projection import project_fields
from lab_generate_skill.teacher.instructions import GUIDE_REVISION3
from map_actor_view_fixtures import original_turn

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
E = (
    W
    / "experiments/framework-context-compression-20261031-v1/complete-comparison-4859843"
)


def checked(reference: dict[str, object]) -> bytes:
    name = reference["path"]
    assert type(name) is str
    raw = (W / name).read_bytes()
    assert len(raw) == reference["bytes"]
    assert hashlib.sha256(raw).hexdigest() == reference["sha256"]
    return raw


def test_final_map_model_bytes_equal_complete_export_with_30825_tokens_and_all_IDs() -> (
    None
):
    manifest = json.loads((E / "manifest.json").read_bytes())
    record = manifest["map"]["variants"][2]
    turn, _ = original_turn()
    actual = build_actor_projection(MapRailsAddressableProjection())(turn)
    assert actual.model_dump_json().encode() == checked(record["complete_input"])
    assert [m.model_dump(mode="json") for m in actual.messages] == json.loads(
        checked(record["complete_messages"])
    )
    assert record["input_tokens"] == 30825 and record["removed_IDs"] == 0
    assert not record["hard_fits"] and not record["sent"]


@pytest.mark.parametrize("round_index", [0, 1, 2])
def test_final_teacher_messages_match_complete_export_and_original_actual_input_stays_separate(
    round_index: int,
) -> None:
    manifest = json.loads((E / "manifest.json").read_bytes())
    record = manifest["teacher"][round_index]
    original = json.loads(checked(record["original_reconstructed_messages"]))
    after = json.loads(checked(record["current_offline_candidate"]))
    expected = project_fields(native_evidence(original[1]["content"]))
    assert after == [
        dict(original[0], content=original[0]["content"] + GUIDE_REVISION3),
        dict(role="user", content=expected.model_dump_json()),
    ]
    actual_stored = json.loads(
        checked(record["original_stored_artifacts"]["actual-input"])
    )
    assert set(actual_stored) == {"messages", "seed", "input_tokens"}
    assert len(actual_stored["messages"]) == 2
    assert actual_stored["messages"] != after
    assert not record["new_candidate_sent"]
