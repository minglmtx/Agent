"""New navigation native lifecycle and existing worker dispatch combination."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationPrepared,
    NavigationRestored,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_lifecycle import (
    AdminNavigationLifecycle,
)
from lab_generate_skill.sites.shopping_admin.worker_instance import AdminWorkerInstance
from lab_generate_skill.sites.shopping_admin.tasks.product_seed_program import (
    PRODUCT_SEED_PHP,
)
from test_admin_navigation_input import contracts as contracts
from admin_navigation_fixtures import case, capture, prepared, restore, request
from admin_navigation_fixtures import command_phase
from test_slurm_commands import guard


def test_snapshot_no_product_prepare_full_state_restore_once(
    tmp_path: Path, contracts: Any
) -> None:
    worker, commands = case(tmp_path)
    first, ref = capture(worker, contracts)
    count = len(commands.calls)
    prepare = first.model_copy(
        update={
            "action": "prepare",
            "snapshot_ref": ref,
            "operation": first.operation.model_copy(update={"operation_id": "prepare"}),
        }
    )
    value = worker.execute_task(prepare, control=guard())
    facts = NavigationPrepared.model_validate_json(value.private_result)
    assert facts.task == first.task and facts.snapshot_ref == ref
    assert (
        worker.snapshot is not None
        and facts.state_snapshot_sha256 == worker.snapshot.state.digest
    )
    assert (
        len(commands.calls) == count
    )  # Navigation has no native target initialization.
    path = tmp_path / "state/app/var/training-mail/message"
    path.write_bytes(b"changed")
    cleanup = restore(prepare, ref)
    result = worker.execute_task(cleanup, control=guard())
    restored = NavigationRestored.model_validate_json(result.private_result)
    assert restored.operation == cleanup.operation and restored.snapshot_ref == ref
    assert path.read_bytes() == b"original"
    assert restored.state.search.original == worker.snapshot.state.search
    assert restored.state.cache.redis_all_databases_empty
    assert restored.state.database.operation == "restore"
    assert [command_phase(x) for x in commands.calls] == [
        "search:save",
        "save",
        "navigation:contents",
        "verify",
        "search:preflight",
        "restore",
        "cache:flush",
        "FLUSHALL",
        "keyspace",
        "search:restore",
    ]
    assert all(PRODUCT_SEED_PHP not in x for x in commands.calls)
    assert (
        worker.phase == "restored"
        and not worker.busy
        and worker.authority.current is None
    )
    count = len(commands.calls)
    for current in (cleanup, prepare, request(contracts, operation_id="new-snapshot")):
        with pytest.raises(InvalidTransition):
            worker.execute_task(current, control=guard())
    assert len(commands.calls) == count


def test_original_snapshot_can_restore_before_prepare(
    tmp_path: Path, contracts: Any
) -> None:
    worker, _ = case(tmp_path)
    first, ref = capture(worker, contracts)
    result = worker.execute_task(restore(first, ref), control=guard())
    assert (
        NavigationRestored.model_validate_json(result.private_result).task == first.task
    )


@pytest.mark.parametrize(
    "fault",
    [
        "sha256",
        "size_bytes",
        "content_schema",
        "visibility",
        "binding",
        "input",
        "attempt_id",
        "allocation_id",
        "run_id",
        "owner_id",
        "recovery_ref",
    ],
)
def test_scope_or_snapshot_change_before_native_effects(
    tmp_path: Path, contracts: Any, fault: str
) -> None:
    worker, commands = case(tmp_path)
    first, ref = capture(worker, contracts)
    current = first.model_copy(
        update={
            "action": "prepare",
            "snapshot_ref": ref,
            "operation": first.operation.model_copy(update={"operation_id": "prepare"}),
        }
    )
    if fault in ("sha256", "size_bytes", "content_schema", "visibility"):
        value = {
            "sha256": "0" * 64,
            "size_bytes": 1,
            "content_schema": "other/1",
            "visibility": "public",
        }[fault]
        current = current.model_copy(
            update={"snapshot_ref": ref.model_copy(update={fault: value})}
        )
    elif fault == "binding":
        current = current.model_copy(
            update={
                "binding_ref": current.binding_ref.model_copy(
                    update={"sha256": "0" * 64}
                )
            }
        )
    elif fault == "input":
        current = current.model_copy(
            update={"private_input": current.private_input + " "}
        )
    else:
        value = (
            ref.model_copy(update={"content_schema": "recovery-plan/1"})
            if fault == "recovery_ref"
            else "different"
        )
        current = current.model_copy(
            update={"operation": current.operation.model_copy(update={fault: value})}
        )
    count = len(commands.calls)
    with pytest.raises((ValueError, OwnershipConflict)):
        worker.execute_task(current, control=guard())
    assert len(commands.calls) == count and worker.phase == "snapshotted"


@pytest.mark.parametrize(
    "fault",
    [
        "frontend",
        "verify",
        "search:preflight",
        "restore",
        "cache:flush",
        "search:restore",
    ],
)
def test_partial_recovery_retains_original_snapshot_and_forbids_resend(
    tmp_path: Path, contracts: Any, fault: str
) -> None:
    worker, commands = case(tmp_path)
    parent = prepared(worker, contracts)
    commands.fail = fault
    cleanup = restore(parent, parent.snapshot_ref)
    with pytest.raises(OSError) as caught:
        worker.execute_task(cleanup, control=guard())
    assert (
        worker.phase == "quarantined"
        and getattr(caught.value, "admin_navigation_recovery_snapshot")
        is worker.snapshot
    )
    assert worker.authority.current is None and not worker.busy
    count = len(commands.calls)
    with pytest.raises(InvalidTransition):
        worker.execute_task(cleanup, control=guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize("when", ["before", "after_known_restore"])
def test_cancellation_preserves_known_restore_and_no_repeat(
    tmp_path: Path, contracts: Any, when: str
) -> None:
    worker, commands = case(tmp_path)
    current = (
        request(contracts)
        if when == "before"
        else restore(prepared(worker, contracts), worker.snapshot_ref)
    )

    class Control:
        def checkpoint(self) -> float:
            if when == "before" or worker.phase == "restored":
                raise OperationStopped("CANCELLED", "test")
            return 30.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped):
        worker.execute_task(current, control=Control())
    if when == "before":
        assert worker.phase == "new" and not commands.calls
    else:
        assert worker.phase == "quarantined" and worker.restore_result is not None
        count = len(commands.calls)
        with pytest.raises(InvalidTransition):
            worker.execute_task(current, control=guard())
        assert len(commands.calls) == count


def test_actual_worker_navigation_dispatch_and_no_native_inspect(
    tmp_path: Path, contracts: Any
) -> None:
    lifecycle, commands = case(tmp_path)
    site: Any = SimpleNamespace(
        state="ready",
        spec=lifecycle.service,
        commands=commands,
        stop_frontend=lifecycle.stop_frontend,
    )
    worker = AdminWorkerInstance(site)
    first = request(contracts)
    worker.execute_task(first, control=guard())
    assert isinstance(worker.tasks, AdminNavigationLifecycle)
    count = len(commands.calls)
    assert isinstance(worker.tasks, AdminNavigationLifecycle)
    assert worker.tasks.snapshot is not None
    from test_admin_description_inputs import reference

    snapshot_ref = reference(
        worker.tasks.snapshot.model_dump_json().encode(),
        content_schema=worker.tasks.snapshot.schema_version,
    )
    inspect = first.model_copy(
        update={
            "action": "inspect",
            "snapshot_ref": snapshot_ref,
            "operation": first.operation.model_copy(
                update={"operation_id": "navigation-inspect"}
            ),
        }
    )
    with pytest.raises(ValueError, match="no live native inspect"):
        worker.execute_task(inspect, control=guard())
    unknown = first.model_copy(
        update={"task": first.task.model_copy(update={"family": "unsupported"})}
    )
    with pytest.raises(ValueError):
        worker.execute_task(unknown, control=guard())
    assert len(commands.calls) == count


def test_existing_product_worker_dispatch_preserves_original_contract(
    tmp_path: Path,
) -> None:
    from test_product_recovery_rpc import Commands
    from test_site_task_execution import request as product_request
    from lab_generate_skill.sites.shopping_admin.tasks.product_lifecycle import (
        AdminProductLifecycle,
    )
    from lab_generate_skill.sites.shopping_admin.tasks.product_recovery_contract import (
        ProductRecoverySnapshot,
    )

    lifecycle, _ = case(tmp_path)
    commands = Commands()
    site: Any = SimpleNamespace(
        state="ready",
        spec=lifecycle.service,
        commands=commands,
        stop_frontend=lifecycle.stop_frontend,
    )
    worker = AdminWorkerInstance(site)
    original = product_request("snapshot", "original-product-snapshot")
    result = worker.execute_task(original, control=guard())
    assert isinstance(worker.tasks, AdminProductLifecycle)
    saved = ProductRecoverySnapshot.model_validate_json(result.private_result)
    assert saved.request == original and saved.product.absent
