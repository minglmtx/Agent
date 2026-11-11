"""Public worker task/capture/restore/resume contracts over coherent fake effects."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.sites.shopping.tasks.order_eta_lifecycle import (
    OrderEtaLifecycle,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_resume import OrderEtaResume
from lab_generate_skill.sites.shopping.tasks.order_eta_recovery import (
    OrderEtaRecoverySnapshot,
    OrderEtaRestored,
    OrderEtaResumed,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_state import OrderEtaState
from shopping_task_fixtures import case, request
from test_shopping_order_eta_inputs import reference
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def snapshot(worker: OrderEtaLifecycle) -> EvidenceRef:
    first = request()
    result = worker.execute_task(first, control=guard())
    saved = OrderEtaRecoverySnapshot.model_validate_json(result.private_result)
    assert saved.request == first
    return reference(
        result.private_result.encode(), content_schema=saved.schema_version
    )


def prepared(worker: OrderEtaLifecycle) -> SiteTaskRequest:
    ref = snapshot(worker)
    first = request("prepare", "eta-prepare", ref)
    measured = OrderEtaState.model_validate_json(
        worker.execute_task(first, control=guard()).private_result
    )
    assert measured.fixture.date == "2023-02-03" and measured.task == first.task
    return first


def cleanup(first: SiteTaskRequest) -> SiteTaskRequest:
    return first.model_copy(
        update={
            "action": "restore",
            "operation": first.operation.cleanup(
                "eta-restore", now=datetime.now(timezone.utc), seconds=30
            ),
        }
    )


def test_complete_original_task_capture_restore_resume(node_path: Path) -> None:
    worker, commands, groups = case(node_path)
    first = prepared(worker)
    inspection = first.model_copy(
        update={
            "action": "inspect",
            "operation": first.operation.model_copy(
                update={"operation_id": "eta-capture"}
            ),
        }
    )
    capture = SiteCaptureRequest(
        inspection=inspection, collector_id="shopping-order-eta", collector_version="1"
    )
    actual = worker.capture_task(capture, control=guard())
    assert actual.request_sha256 == capture.digest
    measured = OrderEtaState.model_validate_json(actual.private_result)
    assert measured.legacy_reference()["object_id"] == "shopping_order_eta:000000148"
    restored_request = cleanup(first)
    result = worker.execute_task(restored_request, control=guard())
    restored = OrderEtaRestored.model_validate_json(result.private_result)
    assert restored.request == restored_request and not commands.initialized
    resume = SiteResumeRequest(
        restore_request=restored_request,
        restore_result_ref=reference(
            result.model_dump_json().encode(), content_schema=result.schema_version
        ),
        operation=restored_request.operation.cleanup(
            "eta-resume", now=datetime.now(timezone.utc), seconds=30
        ),
    )
    recovery = OrderEtaResume(worker)
    reply = recovery.resume_frontend(resume, control=guard())
    observed = OrderEtaResumed.model_validate_json(reply.private_result)
    assert observed.protected == restored.snapshot.protected
    assert len(groups) == 3 and worker.instance.state == "resumed"
    count = len(commands.calls)
    for r in (first, restored_request, inspection, request()):
        with pytest.raises(InvalidTransition):
            worker.execute_task(r, control=guard())
    with pytest.raises(OwnershipConflict):
        recovery.resume_frontend(resume, control=guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize("fault", ["before_initialize", "after_initialize"])
def test_failed_native_initialization_never_replays(
    node_path: Path, fault: str
) -> None:
    worker, commands, groups = case(node_path)
    first = request("prepare", "eta-prepare", snapshot(worker))
    commands.native_fail = fault
    with pytest.raises((OSError, TimeoutError)):
        worker.execute_task(first, control=guard())
    assert worker.phase == "quarantined"
    count = len(commands.calls)
    with pytest.raises(InvalidTransition):
        worker.execute_task(first, control=guard())
    assert len(commands.calls) == count and commands.initialized == (
        fault == "after_initialize"
    )


@pytest.mark.parametrize(
    "change",
    ["binding", "snapshot", "private", "owner", "allocation", "attempt", "recovery"],
)
def test_changed_original_scope_rejected_before_native_call(
    node_path: Path, change: str
) -> None:
    worker, commands, groups = case(node_path)
    first = request("prepare", "eta-prepare", snapshot(worker))
    values: dict[str, Any] = {}
    if change == "binding":
        values["binding_ref"] = first.binding_ref.model_copy(
            update={"producer": "other"}
        )
    elif change == "snapshot":
        assert first.snapshot_ref is not None
        values["snapshot_ref"] = first.snapshot_ref.model_copy(
            update={"sha256": "0" * 64}
        )
    elif change == "private":
        values["private_input"] = first.private_input.replace(
            "2023-02-03", "2023-02-04"
        )
    else:
        key = {
            "owner": "owner_id",
            "allocation": "allocation_id",
            "attempt": "attempt_id",
        }.get(change)
        if key:
            values["operation"] = first.operation.model_copy(update={key: "other"})
        else:
            assert first.operation.recovery_ref is not None
            values["operation"] = first.operation.model_copy(
                update={
                    "recovery_ref": first.operation.recovery_ref.model_copy(
                        update={"producer": "other"}
                    )
                }
            )
    count = len(commands.calls)
    with pytest.raises(OwnershipConflict):
        worker.execute_task(first.model_copy(update=values), control=guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize("changed", ["core", "sales_order", "customer_entity", "quote"])
def test_initializer_cannot_hide_other_native_changes(
    node_path: Path, changed: str
) -> None:
    worker, commands, groups = case(node_path)
    first = request("prepare", "eta-prepare", snapshot(worker))
    if changed == "core":
        commands.changed_core = True
    else:
        commands.changed_table = changed
    with pytest.raises(ValueError, match="changed"):
        worker.execute_task(first, control=guard())
    assert worker.phase == "quarantined"


def test_restore_without_preparation_uses_original_snapshot(node_path: Path) -> None:
    worker, commands, groups = case(node_path)
    ref = snapshot(worker)
    first = request().model_copy(update={"snapshot_ref": ref})
    result = worker.execute_task(cleanup(first), control=guard())
    assert (
        OrderEtaRestored.model_validate_json(
            result.private_result
        ).snapshot.request.operation.operation_id
        == "eta-snapshot"
    )
