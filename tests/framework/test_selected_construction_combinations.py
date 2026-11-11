"""Actual current factory, closed review and v7 export/codec; unit effects only."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.application.export_targets import export_targets
from lab_generate_skill.application.dataset_reader import load_dataset
from lab_generate_skill.adapters.training.dataset_encoding import encode_loaded_dataset
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.policies.dataset_manifest import export_metadata
from construction_multi_task_factory_fixtures import four_current_tasks
from export_targets_fixtures import export_case, UnitChatTokenizer
from selected_construction_combination_fixtures import selected_construction_environment


@pytest.mark.parametrize("local", [False, True])
def test_selected_configuration_positive_original_factory_all_four_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local: bool
) -> None:
    with selected_construction_environment(monkeypatch, local=local):
        with four_current_tasks(tmp_path / "case", monkeypatch) as case:
            selected = case.data.plan.actor_context_configuration_ref
            assert (
                selected is not None
                and case.data.plan.schema_version == "construction-plan/4"
            )
            assert len(case.calls) == len(case.port.tasks) == 4
            assert case.native.loader.session.calls == 4
            for current in case.tasks:
                assert current.task.deps.actors is current.binding
                request = current.task.phases.initialized.actor
                assert request.context_configuration_ref == selected
                assert len(current.completed) == 1
                assert current.task.phases.calls.count("restore") == 1
            progress = case.port.construction.journal.read(
                case.tasks[0].task.plan.read_operation
            )
            assert progress.plan == case.data.plan
            assert len(progress.project().attempts) == 4


@pytest.mark.parametrize("local", [False, True])
def test_selected_v7_original_closed_review_export_load_and_sft_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local: bool
) -> None:
    with selected_construction_environment(monkeypatch, local=local):
        c = export_case(tmp_path / "case", monkeypatch)
        original = c.review.sealed.plan
        assert original.schema_version == "construction-plan/4"
        assert original.actor_context_configuration_ref is not None
        native = c.review.control.source.native.loader.session
        before = native.calls
        assert before == 5
        result = export_targets(c.plan(), c.deps)
        assert result.example_count == 1 and result.kind == "engineering_fixture"
        assert result.dataset_ref is not None
        receipt = evidence_reference(
            result.model_dump_json().encode(), export_metadata("export-receipt/1")
        )
        loaded = load_dataset(c.load_plan(receipt), c.deps)
        assert loaded.manifest is not None
        assert loaded.manifest.template == "webarena-generator-v7-selected-actor"
        row = loaded.examples[0]
        assert row.template == loaded.manifest.template
        assert row.generation_input_ref.content_schema == "generation-input/2"
        assert row.labels.training_data is False
        body = json.loads(row.messages[1].content)
        capabilities = body["actor_capabilities"]
        assert bool(capabilities["conditional_read_tools"]) is local
        assert capabilities["registered_read_tools"] == []
        assert len(body["retrieved_skills"]) == 6
        assert "actor_context_configuration_ref" not in row.messages[1].content
        encoded = encode_loaded_dataset(
            loaded,
            UnitChatTokenizer(),
            max_seq_length=16384,
            control=c.deps.controls.bind(c.plan("encode-selected").operation),
        )
        assert len(encoded) == 1 and encoded[0]["assistant_tokens"] > 0
        assert (
            encoded[0]["labels"][: encoded[0]["prompt_tokens"]]
            == [-100] * encoded[0]["prompt_tokens"]
        )
        assert native.calls == before
