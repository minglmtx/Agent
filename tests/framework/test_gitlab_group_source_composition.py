"""Group shared source adapters; software premises are never live qualification."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.gitlab_group_source import GroupSourceSelection
from lab_generate_skill.bootstrap.gitlab_group_source_qualification import (
    qualify_group_source,
)
from lab_generate_skill.bootstrap.gitlab_group_source_publication import (
    publish_group_source,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from test_gitlab_group_complete_starts import original, PINS
from gitlab_group_source_fixtures import group_source_unit_case
from site_instance_fixtures import node_path as node_path


def contracts_for(source: str) -> list[Any]:
    raw, native, public = original(source)
    ref = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="gitlab-native-contract/1",
            visibility="private",
            producer="group-source-unit",
        ),
    )
    return [(native, ref, public)]


@pytest.mark.parametrize("source", tuple(PINS))
def test_complete_Group_sources_use_same_records_unique_capture_full_reset_and_readonly_scope(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    import gitlab_group_fixtures as inputs
    from test_gitlab_group_complete_starts import W

    monkeypatch.setattr(
        inputs,
        "FIXTURE",
        W
        / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
        / (source + ".json"),
    )
    c = group_source_unit_case(
        tmp_path, node_path, monkeypatch, contracts_for(source), "none"
    )
    assert (
        c.qualified is not None
        and c.qualified.receipt.scope.task.source_task_id == source
    )
    from lab_generate_skill.domain.closed_source_read import ClosedSourceBindingInput
    from lab_generate_skill.domain.errors import OwnershipConflict
    from test_slurm_commands import guard

    facts = c.facts
    baseline = facts.baseline_inputs
    store = c.site.evidence
    binding = ClosedSourceBindingInput(
        binding=baseline.binding,
        public_task=baseline.public_task,
        private_spec_json=store.read(
            baseline.binding.private_spec_ref, guard()
        ).decode(),
        baseline_json=baseline.spec.model_dump_json(),
    )
    op = c.site.op.cleanup(
        "group-qualified-binding-read", now=c.site.clock.utcnow(), seconds=120
    )
    reader = c.read_factory(store, op)
    reader.require_current(c.qualified.material, op)
    assert (
        reader.read(c.qualified.material, guard(120), binding=binding)
        == c.qualified.receipt
    )
    assert (
        reader.read(c.qualified.material, guard(120), binding=binding)
        == c.qualified.receipt
    )
    wrong = binding.model_copy(
        update={
            "public_task": baseline.public_task.model_copy(
                update={"goal": baseline.public_task.goal + " changed"}
            )
        }
    )
    with pytest.raises(OwnershipConflict):
        reader.read(c.qualified.material, guard(120), binding=wrong)


@pytest.mark.parametrize("fault", ["cancel_after_reset", "restore_return_lost"])
def test_Group_source_cancel_and_lost_restore_keep_original_unknown_and_close(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    group_source_unit_case(
        tmp_path, node_path, monkeypatch, contracts_for("e4d658cfba6588f6a386"), fault
    )


@pytest.mark.parametrize("value", [None, "", 0, True, {}, []])
def test_Group_source_untyped_owner_refuses_before_effects(value: Any) -> None:
    with pytest.raises(TypeError):
        qualify_group_source(
            value,
            value,
            value,
            value,
            value,
            value,
            journal=value,
            controls=value,
            clock=value,
            prefix="group",
            metadata_seconds=1,
            source_reads=value,
        )
    with pytest.raises(TypeError):
        publish_group_source(value, value, value, value, source_reads=value)


@pytest.mark.parametrize("source", tuple(PINS))
def test_Group_source_selection_repeats_exact_native_and_preserves_declared_origin(
    source: str,
) -> None:
    raw, native, public = original(source)
    selected = GroupSourceSelection(raw, public)
    assert selected == GroupSourceSelection(raw, public)
    assert (
        selected.public_at("http://127.0.0.1:12001/", None).start_url
        == "http://127.0.0.1:12001" + native["start_path"]
    )
    changed = json.loads(raw)
    changed["goal"] += " changed"
    with pytest.raises(ValueError):
        GroupSourceSelection(json.dumps(changed).encode(), public)
