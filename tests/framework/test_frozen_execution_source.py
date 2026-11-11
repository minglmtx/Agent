"""Frozen source provenance stays separate from current validation ownership."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import EvidenceNotFound, OwnershipConflict
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from construction_storage_fixtures import put
from frozen_execution_source_fixtures import frozen_source_case


def test_actual_source_consumers_keep_original_context_scope_and_parent_claim(
    tmp_path: Path,
) -> None:
    c = frozen_source_case(tmp_path)
    parent = c.parent.source
    claim = c.origin.validation.parent.record.model_dump_json().encode()
    parent_path = tmp_path / "parent" / "claims" / c.binding.key.filename
    assert parent_path.read_bytes() == claim
    assert c.source.schema_version == "execution-task-source/2"
    assert c.source.run.owner != parent.source.run.owner
    raw = parent.data.store.read(parent.source_ref)
    assert (
        ExecutionTaskSource.model_validate_json(raw).model_dump_json().encode() == raw
    )
    assert "frozen_origin" not in json.loads(raw)
    for _ in range(2):
        op = c.plan.read_operation
        facts = c.reader.load(c.plan, op, parent.data.adapter.controls.bind(op))
        assert facts.context == parent.inputs.source
        assert facts.context.scope.owner == parent.source.run.owner
        assert (
            facts.source.run == c.binding.run and facts.source.frozen_origin == c.origin
        )
    assert parent_path.read_bytes() == claim and not c.parent.phases.calls
    assert c.parent.model.calls == c.parent.browser.calls == 0


@pytest.mark.parametrize("mode", ["ordinary-ledger", "missing-origin"])
def test_current_validation_cannot_use_an_ordinary_source_or_claim(
    tmp_path: Path, mode: str
) -> None:
    c = frozen_source_case(tmp_path)
    op = c.plan.read_operation
    if mode == "ordinary-ledger":
        c.reader.claims = c.parent.source.claims
    else:
        ordinary = c.source.model_dump(mode="json")
        ordinary["schema_version"] = "execution-task-source/1"
        ordinary.pop("frozen_origin")
        value = ExecutionTaskSource.model_validate_json(json.dumps(ordinary))
        c.plan = c.plan.model_copy(
            update={
                "source_ref": put(
                    c.parent.source.data.store, value, value.schema_version
                )
            }
        )
    calls = c.contexts.calls
    with pytest.raises(OwnershipConflict, match="claim ledger"):
        c.reader.load(c.plan, op, c.parent.source.data.adapter.controls.bind(op))
    assert c.contexts.calls == calls


@pytest.mark.parametrize("bad", [None, {}, [], True, "invalid"])
def test_source2_requires_a_complete_typed_frozen_origin(
    tmp_path: Path, bad: object
) -> None:
    c = frozen_source_case(tmp_path)
    value = c.source.model_dump(mode="json")
    value["frozen_origin"] = bad
    with pytest.raises((ValueError, RuntimeError)):
        ExecutionTaskSource.model_validate_json(json.dumps(value))


def test_ordinary_source_does_not_silently_accept_a_validation_field(
    tmp_path: Path,
) -> None:
    c = frozen_source_case(tmp_path)
    value = c.parent.source.source.model_dump(mode="json")
    value["frozen_origin"] = None
    with pytest.raises(ValueError, match="forbids"):
        ExecutionTaskSource.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("change", ["manifest", "claim", "context", "private-task"])
def test_wrong_parent_is_rejected_before_loading_its_private_context(
    tmp_path: Path, change: str
) -> None:
    c = frozen_source_case(tmp_path)
    store = c.parent.source.data.store
    old = c.parent.source.source
    if change == "manifest":
        ref = c.origin.parent_source_ref.model_copy(
            update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
        )
    else:
        value = old.model_dump(mode="json")
        if change == "claim":
            value["intent"]["binding"]["claim_ref"]["sha256"] = "a" * 64
        elif change == "context":
            value["source_context_receipt_ref"]["producer"] = "different"
        else:
            value["task"]["registration_id"] = "different"
        changed = ExecutionTaskSource.model_validate_json(json.dumps(value))
        ref = put(store, changed, changed.schema_version)
    origin = FrozenExecutionOrigin(
        validation=c.origin.validation, parent_source_ref=ref
    )
    source = ExecutionTaskSource.model_validate(
        c.source.model_copy(update={"frozen_origin": origin})
    )
    source_ref = put(store, source, source.schema_version)
    plan = c.plan.model_copy(update={"source_ref": source_ref})
    op = plan.read_operation
    calls = c.contexts.calls
    with pytest.raises((OwnershipConflict, EvidenceNotFound)):
        c.reader.load(plan, op, c.parent.source.data.adapter.controls.bind(op))
    assert c.contexts.calls == calls


@pytest.mark.parametrize("which", ["parent", "current", "context"])
def test_reading_a_frozen_source_does_not_cache_live_admission(
    tmp_path: Path, which: str
) -> None:
    c = frozen_source_case(tmp_path)
    op = c.plan.read_operation
    control = c.parent.source.data.adapter.controls.bind(op)
    c.reader.load(c.plan, op, control)
    if which == "context":
        c.contexts.denied = True
    else:
        c.authority.denied = which
    with pytest.raises((OwnershipConflict, PermissionError)):
        c.reader.load(c.plan, op, control)
    assert (
        not c.parent.phases.calls
        and c.parent.model.calls == c.parent.browser.calls == 0
    )
