"""Navigation checks feed the existing immutable preparation record consumer."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.domain.preparation_record import PreparationRecordFailure
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationPrepared,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_preparation_checks import (
    NAVIGATION_PREPARATION_CHECKS,
)
from preparation_record_fixtures import put
from admin_navigation_preparation_fixtures import fixture
from test_admin_navigation_input import contracts as contracts


@pytest.mark.parametrize(
    "initialization",
    [
        "fixed_local_start_not_original_trajectory_start",
        "declared_local_start; original goal unchanged",
    ],
)
def test_original_navigation_preparation_publish_load(
    tmp_path: Path, contracts: Any, initialization: str
) -> None:
    index = next(
        i
        for i, (native, _, _) in enumerate(contracts)
        if native["spec"]["initialization"] == initialization
    )
    c = fixture(tmp_path, contracts, index)
    publication = c.adapter.publish(c.selection, c.request.operation)
    prepared = c.adapter.load(publication, c.request.operation)
    receipt = PreparationReceipt.model_validate_json(
        c.store.read(publication.preparation_ref)
    )
    assert (
        receipt.checks.required == NAVIGATION_PREPARATION_CHECKS
        and receipt.checks.status == "pass"
    )
    assert prepared.public_task.identity == c.request.task == c.snapshot.request.task
    cleanup = c.request.operation.cleanup(
        "navigation-read-reconcile", now=datetime.now(timezone.utc), seconds=30
    )
    assert c.adapter.publish(c.selection, cleanup) == publication
    assert c.adapter.load(publication, cleanup) == prepared
    assert c.authority.calls == 4
    assert not hasattr(prepared, "initial_observation")


@pytest.mark.parametrize(
    "fault",
    [
        "state_snapshot_sha256",
        "private_spec_sha256",
        "start_path",
        "initialization",
        "task",
    ],
)
def test_foreign_preparation_cannot_be_published(
    tmp_path: Path, contracts: Any, fault: str
) -> None:
    c = fixture(tmp_path, contracts)
    result = NavigationPrepared.model_validate_json(c.result.private_result)
    value: Any = "0" * 64 if fault.endswith("sha256") else "/wrong/"
    if fault == "task":
        value = result.task.model_copy(update={"task_id": "foreign"})
    if fault == "initialization":
        value = (
            "declared_local_start; original goal unchanged"
            if result.initialization.startswith("fixed")
            else "fixed_local_start_not_original_trajectory_start"
        )
    bad = result.model_copy(update={fault: value})
    result_ref = put(
        c.store, c.result.model_copy(update={"private_result": bad.model_dump_json()})
    )
    selected = c.selection.model_copy(update={"result_ref": result_ref})
    with pytest.raises(PreparationRecordFailure) as error:
        c.adapter.publish(selected, c.request.operation)
    assert error.value.phase == "verify" and isinstance(
        error.value.primary, OwnershipConflict
    )
    assert not error.value.references and c.authority.calls == 0


@pytest.mark.parametrize(
    "fault",
    [
        "binding_ref",
        "private_input",
        "attempt_id",
        "allocation_id",
        "run_id",
        "owner_id",
        "recovery_ref",
    ],
)
def test_snapshot_lineage_must_match_before_record_authority(
    tmp_path: Path, contracts: Any, fault: str
) -> None:
    c = fixture(tmp_path, contracts)
    old = c.snapshot.request
    assert old.operation.recovery_ref is not None
    if fault == "binding_ref":
        old = old.model_copy(
            update={
                "binding_ref": old.binding_ref.model_copy(update={"sha256": "f" * 64})
            }
        )
    elif fault == "private_input":
        import json
        from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
            NavigationExecutionInput,
        )

        raw = json.loads(old.private_input)
        raw["spec"]["heading"] = "foreign"
        old = old.model_copy(
            update={
                "private_input": NavigationExecutionInput.model_validate_json(
                    json.dumps(raw)
                ).model_dump_json()
            }
        )
    else:
        recovery = old.operation.recovery_ref
        assert recovery is not None
        value: Any = (
            recovery.model_copy(update={"sha256": "f" * 64})
            if fault == "recovery_ref"
            else "foreign"
        )
        old = old.model_copy(
            update={"operation": old.operation.model_copy(update={fault: value})}
        )
    saved = c.snapshot.model_copy(update={"request": old})
    snapshot_ref = put(c.store, saved)
    request = c.request.model_copy(update={"snapshot_ref": snapshot_ref})
    descriptor = NavigationPrepared.model_validate_json(
        c.result.private_result
    ).model_copy(update={"snapshot_ref": snapshot_ref})
    result = c.result.model_copy(
        update={
            "request_sha256": request.digest,
            "private_result": descriptor.model_dump_json(),
        }
    )
    selected = c.selection.model_copy(
        update={
            "request_ref": put(c.store, request),
            "result_ref": put(c.store, result),
        }
    )
    with pytest.raises(PreparationRecordFailure) as caught:
        c.adapter.publish(selected, c.request.operation)
    assert caught.value.phase == "verify" and c.authority.calls == 0


def test_missing_native_record_authority_still_refuses_navigation(
    tmp_path: Path, contracts: Any
) -> None:
    c = fixture(tmp_path, contracts)
    c.authority.denied = True
    with pytest.raises(PreparationRecordFailure) as caught:
        c.adapter.publish(c.selection, c.request.operation)
    assert isinstance(caught.value.primary, PermissionError)
