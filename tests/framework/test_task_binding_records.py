"""Actual task-definition CAS graph, private source recomputation and failures."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.admin_description_records import (
    bind_product_description_records,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_publication import TaskBindingCommitUnconfirmed
from task_binding_fixtures import fixture, TestControls as Controls
from test_run_journal import command


def test_publish_repeat_and_fresh_consumer_reverify_original_bytes_and_authority(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    op = command()
    ref = data.records.publish(data.binding, op)
    assert ref.visibility == "private" and ref.content_schema == "task-binding/1"
    assert data.records.publish(data.binding, op) == ref
    reopened = bind_product_description_records(
        data.store, data.controls, data.authority
    )
    assert reopened.load(ref, command()) == data.binding
    assert len(data.authority.calls) == 3
    assert set(data.store.read_controls + data.store.put_controls) == {
        data.controls.control
    }
    assert data.store.read(data.binding.public_task_ref).find(b"control_steps") == -1
    assert data.store.read(ref) == data.binding.model_dump_json().encode()


@pytest.mark.parametrize(
    "item", ["public_task_ref", "private_spec_ref", "baseline_ref", "native"]
)
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_dependency_bytes_are_read_on_both_publication_and_consumption(
    tmp_path: Path, item: str, fault: str
) -> None:
    data = fixture(tmp_path)
    ref = data.records.publish(data.binding, command())
    target = data.native if item == "native" else getattr(data.binding, item)
    path = tmp_path / "blobs" / target.sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupted")
    before = data.store.puts
    error = EvidenceNotFound if fault == "missing" else EvidenceIntegrityError
    with pytest.raises(error):
        data.records.publish(data.binding, command())
    with pytest.raises(error):
        data.records.load(ref, command())
    assert data.store.puts == before


@pytest.mark.parametrize(
    "change",
    ["description", "product_id", "legacy_runtime_task_id", "task", "duplicate"],
)
def test_private_spec_must_match_recomputed_original(
    tmp_path: Path, change: str
) -> None:
    data = fixture(tmp_path)
    raw = data.store.read(data.binding.private_spec_ref)
    spec = json.loads(raw)
    if change == "duplicate":
        replacement = b'{"description":"wrong",' + raw[1:]
    else:
        if change == "task":
            spec["task"]["task_id"] = "other"
        else:
            spec[change] = {
                "description": "wrong",
                "product_id": 9,
                "legacy_runtime_task_id": "different",
            }[change]
        from lab_generate_skill.sites.shopping_admin.tasks.product_description_spec import (
            ProductDescriptionSpec,
        )

        replacement = (
            ProductDescriptionSpec.model_validate_json(json.dumps(spec))
            .model_dump_json()
            .encode()
        )
    binding = data.binding.model_copy(
        update={
            "private_spec_ref": data.put(
                replacement, "shopping-admin-product-description/1"
            )
        }
    )
    stored = data.put(binding.model_dump_json().encode(), "task-binding/1")
    before = data.store.puts
    for invoke in (
        lambda: data.records.publish(binding, command()),
        lambda: data.records.load(stored, command()),
    ):
        with pytest.raises((ValueError, EvidenceIntegrityError, OwnershipConflict)):
            invoke()
    assert data.store.puts == before


def test_public_identity_mismatch_rejected_before_authority_and_put(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    identity = data.binding.identity.model_copy(update={"split": "test"})
    binding = data.binding.model_copy(update={"identity": identity})
    before = data.store.puts
    with pytest.raises(OwnershipConflict):
        data.records.publish(binding, command())
    assert data.store.puts == before and not data.authority.calls


@pytest.mark.parametrize("fault", ["denied", "wrong_owner", "wrong_baseline", "stop"])
def test_real_authority_dependency_cannot_be_bypassed(
    tmp_path: Path, fault: str
) -> None:
    data = fixture(tmp_path)
    ref = data.records.publish(data.binding, command())
    op = command()
    if fault == "denied":
        data.authority.denied = True
    elif fault == "wrong_owner":
        op = op.model_copy(update={"owner_id": "foreign"})
    elif fault == "wrong_baseline":
        baseline = data.put(b"{}", "unit-admin-baseline/1")
        data.binding = data.binding.model_copy(update={"baseline_ref": baseline})
        ref = data.put(data.binding.model_dump_json().encode(), "task-binding/1")
    else:
        data.authority.stop = True
    before = data.store.puts
    for invoke in (
        lambda: data.records.publish(data.binding, op),
        lambda: data.records.load(ref, op),
    ):
        with pytest.raises((OwnershipConflict, OperationStopped)):
            invoke()
    assert data.store.puts == before


@pytest.mark.parametrize("mode", ["before_put", "after_commit"])
def test_put_error_preserves_original_group_without_retry_or_deletion(
    tmp_path: Path, mode: str
) -> None:
    data = fixture(tmp_path)
    data.store.mode = mode
    before = data.store.puts
    with pytest.raises(ExceptionGroup) as raised:
        data.records.publish(data.binding, command())
    assert raised.value is data.store.original_error
    assert len(raised.value.exceptions) == 2
    assert data.store.puts == before + 1
    if mode == "after_commit":
        assert data.store.last_ref is not None
        data.store.mode = "normal"
        assert data.records.load(data.store.last_ref, command()) == data.binding


def test_stop_after_return_retains_reference_for_read_only_cleanup(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    op = command()
    data.store.mode = "after_return"
    with pytest.raises(TaskBindingCommitUnconfirmed) as raised:
        data.records.publish(data.binding, op)
    assert isinstance(raised.value.__cause__, OperationStopped)
    assert raised.value.reference == data.store.last_ref
    before = data.store.puts
    data.store.mode = "normal"
    fresh_controls = Controls()
    reader = bind_product_description_records(
        data.store, fresh_controls, data.authority
    )
    cleanup = command(cleanup_parent=op.operation_id)
    assert reader.load(raised.value.reference, cleanup) == data.binding
    assert data.store.puts == before
    assert data.authority.calls[-1] == cleanup


def test_wrong_store_reference_is_rejected(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    data.store.mode = "wrong_reference"
    with pytest.raises(EvidenceIntegrityError, match="different task binding"):
        data.records.publish(data.binding, command())


@pytest.mark.parametrize("value", [None, {}, [], True, "task"])
def test_invalid_binding_has_no_io(tmp_path: Path, value: Any) -> None:
    data = fixture(tmp_path)
    before = (data.store.puts, len(data.store.read_controls))
    with pytest.raises(ValueError):
        data.records.publish(value, command())
    assert (data.store.puts, len(data.store.read_controls)) == before


@pytest.mark.parametrize(
    "raw", [b"", b"{}", b"[]", b"null", b'{"identity":{},"identity":{}}']
)
def test_invalid_binding_bytes_never_read_dependencies(
    tmp_path: Path, raw: bytes
) -> None:
    data = fixture(tmp_path)
    ref = data.put(raw, "task-binding/1")
    before = len(data.store.read_controls)
    with pytest.raises(ValueError):
        data.records.load(ref, command())
    assert len(data.store.read_controls) == before + 1
    assert not data.authority.calls


def test_already_stopped_control_does_not_read_or_write(tmp_path: Path) -> None:
    data = fixture(tmp_path)
    ref = data.records.publish(data.binding, command())
    data.controls.control.stopped = True
    before = (data.store.puts, len(data.store.read_controls))
    for invoke in (
        lambda: data.records.publish(data.binding, command()),
        lambda: data.records.load(ref, command()),
    ):
        with pytest.raises(OperationStopped):
            invoke()
    assert (data.store.puts, len(data.store.read_controls)) == before


@pytest.mark.parametrize("value", [None, {}, [], True, "op"])
def test_invalid_operation_has_no_io(tmp_path: Path, value: Any) -> None:
    data = fixture(tmp_path)
    before = (data.store.puts, len(data.store.read_controls))
    with pytest.raises(ValueError):
        data.records.publish(data.binding, value)
    assert (data.store.puts, len(data.store.read_controls)) == before
