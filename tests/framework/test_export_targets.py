"""Original selection/review -> immutable fixture dataset -> old common SFT codec."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.application.export_targets import export_targets
from lab_generate_skill.policies.dataset_manifest import export_metadata
from lab_generate_skill.application.dataset_reader import load_dataset
from lab_generate_skill.adapters.training.dataset_encoding import (
    encode_loaded_dataset,
    supervised_record,
)
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.dataset import DatasetManifest
from export_targets_fixtures import export_case, UnitChatTokenizer


def test_original_selected_review_to_saved_dataset_and_same_SFT_messages_without_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = export_case(tmp_path / "case", monkeypatch)
    plan = c.plan()
    result = export_targets(plan, c.deps)
    assert result.kind == "engineering_fixture" and result.example_count == 1
    assert result.status == "awaiting_goal_groups" and result.dataset_ref is not None
    receipt_ref = evidence_reference(
        result.model_dump_json().encode(), export_metadata("export-receipt/1")
    )
    store = c.review.control.source.data.store
    assert store.read(receipt_ref) == result.model_dump_json().encode()
    loaded = load_dataset(c.load_plan(receipt_ref), c.deps)
    assert (
        loaded.manifest is not None
        and loaded.manifest.items[0].partition == "candidate"
    )
    row = loaded.examples[0]
    assert row.labels.training_data is False and row.labels.teacher_mode == "fixture"
    assert row.target_skill_ref == c.review.fifth.task.plan.skill_ref
    assert (
        json.loads(row.messages[-1].content)
        == c.review.sealed.project().candidates[4].response.skill.model_payload()
    )
    body = json.loads(row.messages[1].content)
    assert len(body["retrieved_skills"]) == 6
    assert "claim_ref" not in body and "evaluator_feedback" not in body
    encoded = encode_loaded_dataset(
        loaded,
        UnitChatTokenizer(),
        max_seq_length=16384,
        control=c.deps.controls.bind(c.plan("encode-control").operation),
    )
    assert len(encoded) == 1 and encoded[0]["assistant_tokens"] > 0
    assert (
        encoded[0]["labels"][: encoded[0]["prompt_tokens"]]
        == [-100] * encoded[0]["prompt_tokens"]
    )
    assert len(encoded[0]["input_ids"]) <= 16384
    assert supervised_record(row)["id"] == row.legacy_id == row.task.task_id
    assert (
        c.review.control.source.native.loader.session.calls == 5
        and len(c.review.control.wire.transport.calls) == 1
    )
