"""Persisted preparation: actual dependency bytes, semantic checks and partial commits."""

from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.preparation import PreparationReceipt, PreparedTask
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparationRecordFailure,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.tasks.product_seed_contract import (
    ProductState,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_execution import (
    ProductExecutionInput,
)
from preparation_record_fixtures import fixture, Case


def test_publish_load_repeat_and_cleanup_do_not_rerun_site(tmp_path: Path) -> None:
    c = fixture(tmp_path)
    pub = c.adapter.publish(c.selection, c.request.operation)
    prepared = c.adapter.load(pub, c.request.operation)
    receipt = PreparationReceipt.model_validate_json(c.store.read(pub.preparation_ref))
    assert (
        prepared.public_task.identity == c.request.task
        and receipt.checks.status == "pass"
    )
    assert (
        receipt.operation == c.request.operation
        and c.environment.checks.status == "unknown"
    )
    assert not hasattr(prepared, "initial_observation")
    cleanup = c.request.operation.cleanup(
        "reconcile", now=datetime.now(timezone.utc), seconds=30
    )
    assert c.adapter.publish(c.selection, cleanup) == pub
    assert c.adapter.load(pub, cleanup) == prepared
    assert c.authority.calls == 4


@pytest.mark.parametrize("field", ["request_ref", "result_ref", "environment_ref"])
@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_actual_dependency_loss_rejects_without_publication(
    tmp_path: Path, field: str, fault: str
) -> None:
    c = fixture(tmp_path)
    ref = getattr(c.selection, field)
    path = tmp_path / "evidence/blobs" / ref.sha256
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(b"bad")
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises(PreparationRecordFailure) as e:
        c.adapter.publish(c.selection, c.request.operation)
    assert e.value.phase == "verify" and not e.value.references
    assert set((tmp_path / "evidence/blobs").iterdir()) == before


@pytest.mark.parametrize(
    "change",
    [
        "digest",
        "inspect",
        "scope",
        "spec",
        "recovery",
        "same_operation",
        "snapshot",
        "seed",
        "measurement",
        "coverage",
    ],
)
def test_mismatch_rejected_before_publication(tmp_path: Path, change: str) -> None:
    c = fixture(tmp_path)
    request, result, env = c.request, c.result, c.environment
    if change == "digest":
        result = result.model_copy(update={"request_sha256": "0" * 64})
    elif change == "inspect":
        request = request.model_copy(update={"action": "inspect"})
    elif change == "scope":
        request = request.model_copy(
            update={
                "operation": request.operation.model_copy(
                    update={"attempt_id": "different"}
                )
            }
        )
    elif change == "spec":
        env = env.model_copy(
            update={"spec_ref": env.spec_ref.model_copy(update={"sha256": "f" * 64})}
        )
    elif change == "recovery":
        request = request.model_copy(
            update={
                "operation": request.operation.model_copy(
                    update={"recovery_ref": env.allocation.recovery_ref}
                )
            }
        )
    elif change == "same_operation":
        env = env.model_copy(update={"operation": request.operation})
    elif change == "snapshot":
        snap = c.snapshot.model_copy(
            update={
                "request": c.snapshot.request.model_copy(
                    update={
                        "binding_ref": c.snapshot.request.binding_ref.model_copy(
                            update={"producer": "other"}
                        )
                    }
                )
            }
        )
        request = request.model_copy(update={"snapshot_ref": c.put(snap)})
    elif change == "seed":
        data = ProductExecutionInput.model_validate_json(request.private_input)
        value = data.seed.scenario.products[0].model_copy(update={"price": "99.99"})
        data = data.model_copy(
            update={
                "seed": data.seed.model_copy(
                    update={
                        "scenario": data.seed.scenario.model_copy(
                            update={"products": (value,)}
                        )
                    }
                )
            }
        )
        request = request.model_copy(update={"private_input": data.model_dump_json()})
    elif change == "measurement":
        result = result.model_copy(
            update={
                "private_result": ProductState.model_validate_json(
                    result.private_result
                )
                .model_copy(update={"description": "already filled"})
                .model_dump_json()
            }
        )
    else:
        spec = c.adapter.reader.load(
            c.selection,
            c.request.operation,
            c.adapter.controls.bind(c.request.operation),
        ).spec
        new = spec.model_copy(update={"preparation_checks": ("different",)})
        newref = c.put(new)
        binding = c.adapter.reader.bindings.load(
            request.binding_ref, c.request.operation
        ).model_copy(update={"baseline_ref": newref})
        request = request.model_copy(update={"binding_ref": c.put(binding)})
        env = env.model_copy(update={"spec_ref": newref})
    if change != "digest":
        result = result.model_copy(update={"request_sha256": request.digest})
    selection = PreparationSelection(
        request_ref=c.put(request), result_ref=c.put(result), environment_ref=c.put(env)
    )
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises(PreparationRecordFailure):
        c.adapter.publish(selection, request.operation)
    assert set((tmp_path / "evidence/blobs").iterdir()) == before


@pytest.mark.parametrize(
    "change", ["parent", "owner", "attempt", "allocation", "recovery"]
)
def test_cleanup_cannot_change_original_scope(tmp_path: Path, change: str) -> None:
    c = fixture(tmp_path)
    op = c.request.operation.cleanup(
        "reconcile", now=datetime.now(timezone.utc), seconds=30
    )
    mapping = {
        "parent": "parent_operation_id",
        "owner": "owner_id",
        "attempt": "attempt_id",
        "allocation": "allocation_id",
        "recovery": "recovery_ref",
    }
    value: Any = "other"
    if change == "recovery":
        value = c.environment.allocation.recovery_ref
    op = op.model_copy(update={mapping[change]: value})
    with pytest.raises(PreparationRecordFailure):
        c.adapter.publish(c.selection, op)


@pytest.mark.parametrize("which", ["preparation", "prepared"])
def test_forged_output_rejected_on_load(tmp_path: Path, which: str) -> None:
    c = fixture(tmp_path)
    pub = c.adapter.publish(c.selection, c.request.operation)
    if which == "preparation":
        old = PreparationReceipt.model_validate_json(c.store.read(pub.preparation_ref))
        new = old.model_copy(
            update={
                "operation": old.operation.model_copy(update={"operation_id": "forged"})
            }
        )
        pub = pub.model_copy(update={"preparation_ref": c.put(new)})
    else:
        oldp = PreparedTask.model_validate_json(c.store.read(pub.prepared_ref))
        newp = oldp.model_copy(
            update={
                "public_task": oldp.public_task.model_copy(update={"goal": "forged"})
            }
        )
        pub = pub.model_copy(update={"prepared_ref": c.put(newp)})
    with pytest.raises(OwnershipConflict):
        c.adapter.load(pub, c.request.operation)


def test_permissions_rechecked_on_read_and_republish(tmp_path: Path) -> None:
    c = fixture(tmp_path)
    pub = c.adapter.publish(c.selection, c.request.operation)
    c.authority.denied = True
    with pytest.raises(PreparationRecordFailure):
        c.adapter.publish(c.selection, c.request.operation)
    with pytest.raises(PermissionError):
        c.adapter.load(pub, c.request.operation)


@pytest.mark.parametrize("stage", [1, 2])
@pytest.mark.parametrize("fault", ["before", "after", "bad_ref", "checkpoint"])
def test_publication_failure_retains_exact_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: int, fault: str
) -> None:
    c = fixture(tmp_path)
    original = c.store.put
    count = 0
    committed: list[EvidenceRef] = []

    def put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        nonlocal count
        count += 1
        if count == stage and fault == "before":
            raise OSError("put before")
        ref = original(data, metadata, control=control)
        committed.append(ref)
        if count == stage:
            if fault == "after":
                raise OSError("put after")
            if fault == "bad_ref":
                return ref.model_copy(update={"sha256": "0" * 64})
            if fault == "checkpoint":

                def stopped() -> float:
                    raise OSError("stopped after commit")

                monkeypatch.setattr(control, "checkpoint", stopped)
        return ref

    monkeypatch.setattr(c.store, "put", put)
    with pytest.raises(PreparationRecordFailure) as error:
        c.adapter.publish(c.selection, c.request.operation)
    assert error.value.phase == ("preparation" if stage == 1 else "prepared")
    assert len(error.value.references) == (
        stage if fault in ("bad_ref", "checkpoint") else stage - 1
    )
    assert error.value.primary is error.value.__cause__
    assert all(c.store.read(ref) for ref in committed)
    monkeypatch.undo()
    pub = c.adapter.publish(c.selection, c.request.operation)
    assert (
        c.adapter.load(pub, c.request.operation).public_task.identity == c.request.task
    )


@pytest.mark.parametrize("bad", [None, {}, [], "", 1])
def test_invalid_selection_has_no_writes(tmp_path: Path, bad: Any) -> None:
    c = fixture(tmp_path)
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises((ValidationError, TypeError)):
        c.adapter.publish(bad, c.request.operation)
    assert before == set((tmp_path / "evidence/blobs").iterdir())


@pytest.mark.parametrize("change", ["product", "instance"])
def test_snapshot_must_match_original_product_and_instance(
    tmp_path: Path, change: str
) -> None:
    c = fixture(tmp_path)
    snap = c.snapshot
    if change == "product":
        snap = snap.model_copy(
            update={"product": snap.product.model_copy(update={"product_id": 999})}
        )
    else:
        state = snap.state
        plan = state.plan
        service = plan.service
        # Construct valid components with a different original instance.
        service = service.model_copy(
            update={
                "layout": service.layout.model_copy(update={"instance_id": "another"})
            }
        )
        artifacts = plan.artifacts.model_copy(update={"instance_id": "another"})
        plan = plan.model_copy(update={"service": service, "artifacts": artifacts})
        state = state.model_copy(
            update={
                "plan": plan,
                "database": state.database.model_copy(
                    update={"layout": service.layout}
                ),
                "artifacts": state.artifacts.model_copy(update={"layout": artifacts}),
            }
        )
        snap = snap.model_copy(update={"state": state})
    req = c.request.model_copy(update={"snapshot_ref": c.put(snap)})
    result = c.result.model_copy(update={"request_sha256": req.digest})
    selection = c.selection.model_copy(
        update={"request_ref": c.put(req), "result_ref": c.put(result)}
    )
    with pytest.raises(PreparationRecordFailure) as e:
        c.adapter.publish(selection, req.operation)
    assert e.value.phase == "verify" and not e.value.references


@pytest.mark.parametrize("value", [None, True, 1, {}, []])
def test_product_measurement_types_are_not_coerced(tmp_path: Path, value: Any) -> None:
    c = fixture(tmp_path)
    data = json.loads(c.result.private_result)
    data["is_in_stock"] = value
    # True is a valid boolean but the declared initial fixture requires False.
    result = c.result.model_copy(
        update={"private_result": json.dumps(data, separators=(",", ":"))}
    )
    selection = c.selection.model_copy(update={"result_ref": c.put(result)})
    with pytest.raises(PreparationRecordFailure):
        c.adapter.publish(selection, c.request.operation)


@pytest.mark.parametrize("count", [0, 2])
def test_product_fixture_cardinality_rejected_before_native_effects(
    tmp_path: Path, count: int
) -> None:
    from test_admin_product_seed import seed, Commands
    from test_admin_services import spec
    from test_admin_description_inputs import load, FIXTURE
    from lab_generate_skill.sites.shopping_admin.tasks.product_seed import (
        AdminProductSeed,
    )

    value = seed()
    value = value.model_copy(
        update={
            "scenario": value.scenario.model_copy(
                update={"products": value.scenario.products * count}
            )
        }
    )
    commands = Commands()
    with pytest.raises(ValueError):
        AdminProductSeed(
            spec(tmp_path), load(FIXTURE.read_bytes()).private_spec, value, commands
        )
    assert not commands.calls


def test_native_receipt_fixture_uses_original_endpoint_and_no_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from site_resource_fixtures import resource_case
    from site_preparation_native import NativePreparation

    c = resource_case(tmp_path, monkeypatch)
    support = NativePreparation(c, "http://127.0.0.1:12345/admin")
    assert (
        support.public.start_url
        == "http://127.0.0.1:12345/admin/catalog/product/edit/id/2041/store/0/"
    )
    assert (
        support.request is None
        and support.result is None
        and support.environment is None
    )
    assert support.bindings.load(support.binding_ref, c.op) == support.binding
    read_op = support.resource_read_operation(c.op)
    assert (
        read_op.deadline == c.op.deadline
        and read_op.attempt_id == c.spec.token.attempt_id
    )
    assert (
        read_op.recovery_ref == c.spec.token.recovery_ref and read_op.mode == "cleanup"
    )
    assert not c.channels


@pytest.mark.parametrize("change", ["schema", "visibility", "media", "missing"])
def test_selection_refs_are_strict_before_io(tmp_path: Path, change: str) -> None:
    c = fixture(tmp_path)
    data = c.selection.model_dump()
    if change == "missing":
        data.pop("result_ref")
    else:
        name = {
            "schema": "content_schema",
            "visibility": "visibility",
            "media": "media_type",
        }[change]
        data["result_ref"][name] = {
            "schema": "site-task-result/0",
            "visibility": "public",
            "media": "text/plain",
        }[change]
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises(ValidationError):
        PreparationSelection.model_validate(data)
    assert before == set((tmp_path / "evidence/blobs").iterdir())


@pytest.mark.parametrize(
    "field,value",
    [
        ("restore_component_version", "1"),
        ("restore_component_version", "2"),
        ("restore_component_id", "other"),
    ],
)
def test_preparation_rejects_old_or_foreign_recovery_component(
    tmp_path: Path, field: str, value: str
) -> None:
    from test_slurm_commands import guard

    c = fixture(tmp_path)
    inputs = c.adapter.reader.load(c.selection, c.request.operation, guard())
    assert inputs.recovery.restore_component_version == "3"
    changed = inputs.model_copy(
        update={"recovery": inputs.recovery.model_copy(update={field: value})}
    )
    before = set((tmp_path / "evidence/blobs").iterdir())
    with pytest.raises(ValueError, match="Unsupported product recovery component"):
        c.adapter.checks.check(changed, guard())
    assert set((tmp_path / "evidence/blobs").iterdir()) == before
