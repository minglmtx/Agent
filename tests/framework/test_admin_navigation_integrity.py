"""Held original recovery verification, not an additional business predicate."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_integrity import (
    NavigationSnapshotIntegrity,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationRecoverySnapshot,
    NavigationRestored,
)
from admin_navigation_fixtures import case, prepared, restore, command_phase
from test_admin_navigation_contents import ReturnedCancellation
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


def inspection(parent: SiteTaskRequest) -> SiteCaptureRequest:
    return SiteCaptureRequest(
        inspection=parent.model_copy(
            update={
                "action": "inspect",
                "operation": parent.operation.model_copy(
                    update={"operation_id": "native-guard"}
                ),
            }
        ),
        collector_id="admin-navigation-snapshot-integrity",
        collector_version="1",
    )


def test_verify_only_original_backups_then_restore_changed_live_state(
    tmp_path: Path, contracts: Any
) -> None:
    worker, commands = case(tmp_path)
    parent = prepared(worker, contracts)
    assert worker.snapshot is not None
    original = worker.snapshot.model_dump_json()
    path = tmp_path / "state/app/var/training-mail/message"
    path.write_bytes(b"actual changed live state; not a page judgment")
    count = len(commands.calls)
    request = inspection(parent)
    result = worker.capture_task(request, control=guard())
    assert result.request_sha256 == request.digest
    facts = NavigationSnapshotIntegrity.model_validate_json(result.private_result)
    facts.require_original(worker.snapshot)
    assert [command_phase(c) for c in commands.calls[count:]] == [
        "verify",
        "search:verify",
    ]
    assert worker.snapshot.model_dump_json() == original and worker.phase == "prepared"
    assert path.read_bytes().startswith(b"actual changed")
    with pytest.raises(InvalidTransition):
        worker.capture_task(request, control=guard())
    fresh = request.model_copy(
        update={
            "inspection": request.inspection.model_copy(
                update={
                    "operation": request.operation.model_copy(
                        update={"operation_id": "new-guard"}
                    )
                }
            )
        }
    )
    with pytest.raises(InvalidTransition):
        worker.capture_task(fresh, control=guard())
    restored = worker.execute_task(
        restore(parent, parent.snapshot_ref), control=guard()
    )
    assert (
        NavigationRestored.model_validate_json(restored.private_result).task
        == parent.task
    )
    assert path.read_bytes() == b"original"


@pytest.mark.parametrize("fault", ["scope", "snapshot", "collector", "cancel_before"])
def test_invalid_guard_has_no_native_effects_or_permission(
    tmp_path: Path, contracts: Any, fault: str
) -> None:
    worker, commands = case(tmp_path)
    parent = prepared(worker, contracts)
    request = inspection(parent)
    if fault == "collector":
        request = request.model_copy(update={"collector_id": "admin-product-catalog"})
    elif fault == "scope":
        request = request.model_copy(
            update={
                "inspection": request.inspection.model_copy(
                    update={
                        "operation": request.operation.model_copy(
                            update={"attempt_id": "foreign"}
                        )
                    }
                )
            }
        )
    elif fault == "snapshot":
        ref = request.inspection.snapshot_ref
        assert ref is not None
        request = request.model_copy(
            update={
                "inspection": request.inspection.model_copy(
                    update={"snapshot_ref": ref.model_copy(update={"sha256": "0" * 64})}
                )
            }
        )
    count = len(commands.calls)
    with pytest.raises((ValueError, OwnershipConflict, OperationStopped)):
        worker.capture_task(
            request, control=guard(0) if fault == "cancel_before" else guard()
        )
    assert len(commands.calls) == count and not worker.integrity_attempted


def test_partial_failed_verification_retains_prefix_and_no_redispatch(
    tmp_path: Path, contracts: Any
) -> None:
    worker, commands = case(tmp_path)
    parent = prepared(worker, contracts)
    commands.fail = "search:verify"
    with pytest.raises(OSError, match="failed-search:verify") as caught:
        worker.capture_task(inspection(parent), control=guard())
    assert getattr(caught.value, "admin_navigation_integrity_database") is not None
    assert getattr(caught.value, "admin_navigation_integrity_artifacts") is not None
    assert getattr(caught.value, "admin_navigation_integrity_returned_result") is None
    assert (
        worker.phase == "quarantined"
        and worker.authority.current is None
        and not worker.busy
    )
    count = len(commands.calls)
    with pytest.raises(InvalidTransition):
        worker.capture_task(inspection(parent), control=guard())
    assert len(commands.calls) == count


def test_post_return_cancellation_retains_verified_guard_not_committed_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> None:
    worker, _ = case(tmp_path)
    parent = prepared(worker, contracts)
    control = ReturnedCancellation()
    original = NavigationSnapshotIntegrity.require_original

    def after(
        self: NavigationSnapshotIntegrity, saved: NavigationRecoverySnapshot
    ) -> None:
        original(self, saved)
        control.returned = True

    monkeypatch.setattr(NavigationSnapshotIntegrity, "require_original", after)
    with pytest.raises(OperationStopped) as caught:
        worker.capture_task(inspection(parent), control=control)
    obtained = getattr(caught.value, "admin_navigation_integrity_returned_result")
    assert obtained is not None
    assert (
        NavigationSnapshotIntegrity.model_validate_json(obtained.private_result).task
        == parent.task
    )
    assert worker.phase == "quarantined" and worker.authority.current is None
