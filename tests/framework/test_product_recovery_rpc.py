"""Actual filesystem snapshots with native task boundary fakes; no production right."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.tasks.product_lifecycle import (
    AdminProductLifecycle,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_execution import (
    ProductExecutionInput,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_recovery_contract import (
    ProductAbsence,
    ProductRecoverySnapshot,
    ProductRestored,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_restore_program import (
    PRODUCT_ABSENCE_PHP,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_seed_program import (
    PRODUCT_SEED_PHP,
)
from test_admin_state import Commands as StateCommands
from test_admin_product_seed import record
from test_admin_services import spec
from test_admin_description_inputs import reference
from test_site_task_execution import request
from test_slurm_commands import guard
from frontend_fixtures import frontend


class Commands(StateCommands):
    def __init__(self) -> None:
        super().__init__()
        self.product_exists = False
        self.absence_reads = 0

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        if PRODUCT_ABSENCE_PHP in argv:
            self.calls.append(argv)
            self.absence_reads += 1
            if self.fail == "absence":
                raise OSError("absence failed")
            absent = not self.product_exists and not (
                self.fail == "restored_absence" and self.absence_reads > 1
            )
            return (
                ProductAbsence(product_id=int(argv[-1]), absent=absent)
                .model_dump_json()
                .encode()
            )
        if PRODUCT_SEED_PHP in argv:
            self.calls.append(argv)
            mode = json.loads(argv[-1])["operation"]
            if self.fail == mode:
                raise OSError("product " + mode + " failed")
            if mode == "initialize":
                self.product_exists = True
            assert self.product_exists
            return record().model_dump_json().encode()
        result = super().run(argv, control)
        if argv[-3] == "restore":
            self.product_exists = False
        return result


def case(root: Path) -> tuple[AdminProductLifecycle, Commands]:
    (root / "state/app/var/training-mail").mkdir(parents=True)
    (root / "state/app/var/training-mail/message").write_bytes(b"original")
    commands = Commands()

    def stop_frontend(control: OperationControl) -> Any:
        control.checkpoint()
        if commands.fail == "frontend":
            raise OSError("frontend stop failed")
        return frontend(spec(root))

    return AdminProductLifecycle(spec(root), commands, stop_frontend), commands


def capture(worker: AdminProductLifecycle) -> tuple[SiteTaskRequest, Any]:
    first = request("snapshot", "task-snapshot")
    result = worker.execute_task(first, control=guard())
    snap = ProductRecoverySnapshot.model_validate_json(result.private_result)
    assert snap.request == first and snap.product.absent
    return first, reference(
        result.private_result.encode(), content_schema=snap.schema_version
    )


def prepare(worker: AdminProductLifecycle) -> SiteTaskRequest:
    _, ref = capture(worker)
    req = request().model_copy(update={"snapshot_ref": ref})
    worker.execute_task(req, control=guard())
    return req


def cleanup(
    parent: SiteTaskRequest, snapshot_ref: Any, **changes: Any
) -> SiteTaskRequest:
    op = parent.operation.cleanup(
        "task-restore", now=datetime.now(timezone.utc), seconds=30
    )
    op = op.model_copy(update=changes)
    return parent.model_copy(
        update={"action": "restore", "snapshot_ref": snapshot_ref, "operation": op}
    )


def test_original_snapshot_prepare_inspect_restore_and_no_implicit_reuse(
    tmp_path: Path,
) -> None:
    worker, commands = case(tmp_path)
    prepared = prepare(worker)
    read = prepared.model_copy(
        update={
            "action": "inspect",
            "operation": prepared.operation.model_copy(
                update={"operation_id": "task-inspect"}
            ),
        }
    )
    worker.execute_task(read, control=guard())
    path = tmp_path / "state/app/var/training-mail/message"
    path.write_bytes(b"changed")
    restore = cleanup(prepared, prepared.snapshot_ref)
    result = worker.execute_task(restore, control=guard())
    facts = ProductRestored.model_validate_json(result.private_result)
    assert (
        facts.operation == restore.operation
        and facts.snapshot_ref == prepared.snapshot_ref
    )
    assert (
        facts.product.absent
        and not commands.product_exists
        and path.read_bytes() == b"original"
    )
    assert (
        worker.phase == "restored"
        and not worker.busy
        and worker.authority.current is None
    )
    calls = len(commands.calls)
    for r in (restore, prepared, read, request("snapshot", "new-snapshot")):
        with pytest.raises(InvalidTransition):
            worker.execute_task(r, control=guard())
    assert len(commands.calls) == calls


def test_cleanup_without_successful_prepare_uses_original_snapshot(
    tmp_path: Path,
) -> None:
    worker, commands = case(tmp_path)
    parent, ref = capture(worker)
    result = worker.execute_task(cleanup(parent, ref), control=guard())
    assert ProductRestored.model_validate_json(result.private_result).product.absent
    assert all(PRODUCT_SEED_PHP not in c for c in commands.calls)


@pytest.mark.parametrize("action", ["prepare", "inspect", "restore"])
def test_no_snapshot_no_effect(tmp_path: Path, action: str) -> None:
    worker, commands = case(tmp_path)
    r = request() if action != "restore" else cleanup(request(), request().snapshot_ref)
    if action != "restore":
        r = r.model_copy(update={"action": action})
    with pytest.raises(InvalidTransition):
        worker.execute_task(r, control=guard())
    assert not commands.calls


@pytest.mark.parametrize(
    "field", ["sha256", "size_bytes", "content_schema", "visibility"]
)
def test_wrong_snapshot_reference_cannot_initialize(tmp_path: Path, field: str) -> None:
    worker, commands = case(tmp_path)
    _, ref = capture(worker)
    before = len(commands.calls)
    changed = {
        "sha256": "0" * 64,
        "size_bytes": 1,
        "content_schema": "other/1",
        "visibility": "public",
    }[field]
    r = request().model_copy(
        update={"snapshot_ref": ref.model_copy(update={field: changed})}
    )
    with pytest.raises((ValueError, OwnershipConflict)):
        worker.execute_task(r, control=guard())
    assert len(commands.calls) == before and not commands.product_exists


@pytest.mark.parametrize(
    "field",
    [
        "attempt_id",
        "run_id",
        "owner_id",
        "allocation_id",
        "recovery_ref",
        "parent_operation_id",
    ],
)
def test_restore_cannot_change_scope_or_parent(tmp_path: Path, field: str) -> None:
    worker, commands = case(tmp_path)
    prepared = prepare(worker)
    before = len(commands.calls)
    value: Any = "foreign"
    if field == "recovery_ref":
        value = reference(b"foreign", content_schema="recovery-plan/1")
    with pytest.raises((ValueError, OwnershipConflict)):
        worker.execute_task(
            cleanup(prepared, prepared.snapshot_ref, **{field: value}), control=guard()
        )
    assert len(commands.calls) == before and commands.product_exists


@pytest.mark.parametrize(
    "point",
    [
        "absence",
        "save",
        "search:save",
        "search:preflight",
        "search:restore",
        "frontend",
        "initialize",
        "inspect",
        "verify",
        "restore",
        "FLUSHALL",
        "restored_absence",
    ],
)
def test_each_failure_quarantines_original_and_clears_delegate(
    tmp_path: Path, point: str
) -> None:
    worker, commands = case(tmp_path)
    if point in ("absence", "save", "search:save"):
        r = request("snapshot", "snapshot")
    else:
        _, ref = capture(worker)
        r = request().model_copy(update={"snapshot_ref": ref})
        if point != "initialize":
            worker.execute_task(r, control=guard())
            r = (
                r.model_copy(
                    update={
                        "action": "inspect",
                        "operation": r.operation.model_copy(
                            update={"operation_id": "read"}
                        ),
                    }
                )
                if point == "inspect"
                else cleanup(r, ref)
            )
    commands.fail = point
    with pytest.raises((OSError, ValueError)) as caught:
        worker.execute_task(r, control=guard())
    assert (
        worker.phase == "quarantined"
        and not worker.busy
        and worker.authority.current is None
    )
    assert getattr(caught.value, "admin_product_recovery_snapshot") == worker.snapshot
    n = len(commands.calls)
    with pytest.raises(InvalidTransition):
        worker.execute_task(r, control=guard())
    assert len(commands.calls) == n


def test_existing_product_rejected_before_snapshot_write(tmp_path: Path) -> None:
    worker, commands = case(tmp_path)
    commands.product_exists = True
    with pytest.raises(ValueError):
        worker.execute_task(request("snapshot", "snapshot"), control=guard())
    assert len(commands.calls) == 1 and PRODUCT_ABSENCE_PHP in commands.calls[0]
    assert (
        not worker.state.save_attempted and not worker.state.artifacts.backup.exists()
    )


def test_restore_uses_exact_frozen_reference_including_metadata(tmp_path: Path) -> None:
    worker, commands = case(tmp_path)
    prepared = prepare(worker)
    assert prepared.snapshot_ref is not None
    different = prepared.snapshot_ref.model_copy(update={"producer": "another"})
    with pytest.raises(OwnershipConflict):
        worker.execute_task(cleanup(prepared, different), control=guard())
    assert commands.product_exists


def test_state_delegate_cannot_be_used_outside_current_authorized_command(
    tmp_path: Path,
) -> None:
    worker, commands = case(tmp_path)
    with pytest.raises(PermissionError):
        worker.state.save(guard())
    assert not commands.calls and not worker.state.save_attempted


def test_bad_fixture_rejected_before_snapshot_effects(tmp_path: Path) -> None:
    worker, commands = case(tmp_path)
    r = request("snapshot", "snapshot")
    data = ProductExecutionInput.model_validate_json(r.private_input)
    data = data.model_copy(
        update={"spec": data.spec.model_copy(update={"store_id": 1})}
    )
    with pytest.raises(ValueError):
        worker.execute_task(
            r.model_copy(update={"private_input": data.model_dump_json()}),
            control=guard(),
        )
    assert not commands.calls


@pytest.mark.parametrize("phase", ["save", "verify", "preflight", "restore"])
def test_search_delegate_rejects_outside_parent_command(
    tmp_path: Path, phase: str
) -> None:
    worker, commands = case(tmp_path)
    _, _ = capture(worker)
    assert worker.snapshot is not None
    before = len(commands.calls)
    with pytest.raises(PermissionError):
        worker.state.search.authority.verify(worker.service, phase, None if phase == "save" else worker.snapshot.state.search, guard())  # type: ignore[arg-type]
    assert len(commands.calls) == before


def test_old_product_snapshot_schema_rejected(tmp_path: Path) -> None:
    worker, commands = case(tmp_path)
    capture(worker)
    assert worker.snapshot is not None
    old = worker.snapshot.model_dump()
    old["schema_version"] = "admin-product-recovery/1"
    with pytest.raises(ValueError):
        ProductRecoverySnapshot.model_validate(old)


def test_frontend_failure_prevents_database_restore(tmp_path: Path) -> None:
    worker, commands = case(tmp_path)
    prepared = prepare(worker)
    before = len(commands.calls)
    commands.fail = "frontend"
    with pytest.raises(OSError):
        worker.execute_task(cleanup(prepared, prepared.snapshot_ref), control=guard())
    assert len(commands.calls) == before and commands.product_exists
    assert worker.phase == "quarantined"


def test_frontend_fact_cannot_change_service(tmp_path: Path) -> None:
    worker, commands = case(tmp_path)
    prepared = prepare(worker)
    foreign = worker.service.model_copy(
        update={"ports": worker.service.ports.model_copy(update={"web": 13001})}
    )
    worker.stop_frontend = lambda control: frontend(foreign)
    before = len(commands.calls)
    with pytest.raises(OwnershipConflict):
        worker.execute_task(cleanup(prepared, prepared.snapshot_ref), control=guard())
    assert len(commands.calls) == before and commands.product_exists
