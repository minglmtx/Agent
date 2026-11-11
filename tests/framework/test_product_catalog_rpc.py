"""Catalog capture shares original prepared lifecycle and operation guard."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.product_catalog_program import (
    PRODUCT_CATALOG_PHP,
)
from lab_generate_skill.sites.shopping_admin.product_catalog_contract import (
    ProductCatalogState,
)
from test_product_recovery_rpc import case, prepare, cleanup
from test_site_task_execution import request
from test_admin_product_catalog import state
from test_slurm_commands import guard


def test_capture_before_after_and_restore_share_original_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, commands = case(tmp_path)
    first = SiteCaptureRequest(
        inspection=request("inspect", "too-early"),
        collector_id="admin-product-catalog",
        collector_version="1",
    )
    with pytest.raises(InvalidTransition):
        worker.capture_task(first, control=guard())
    prepared = prepare(worker)
    native = commands.run
    count = 0

    def run(argv: tuple[str, ...], control: OperationControl) -> bytes:
        nonlocal count
        if PRODUCT_CATALOG_PHP in argv:
            count += 1
            commands.calls.append(argv)
            return state().model_dump_json().encode()
        return native(argv, control)

    monkeypatch.setattr(commands, "run", run)
    for index in range(2):
        inspection = prepared.model_copy(
            update={
                "action": "inspect",
                "operation": prepared.operation.model_copy(
                    update={"operation_id": "catalog-" + str(index)}
                ),
            }
        )
        capture = SiteCaptureRequest(
            inspection=inspection,
            collector_id="admin-product-catalog",
            collector_version="1",
        )
        result = worker.capture_task(capture, control=guard())
        assert (
            result.request_sha256 == capture.digest
            and ProductCatalogState.model_validate_json(result.private_result)
            == state()
        )
        with pytest.raises(InvalidTransition):
            worker.capture_task(capture, control=guard())
    assert count == 2 and worker.phase == "prepared"
    worker.execute_task(cleanup(prepared, prepared.snapshot_ref), control=guard(10))
    with pytest.raises(InvalidTransition):
        worker.capture_task(first, control=guard())
    assert count == 2


@pytest.mark.parametrize(
    "failure", ["collector", "version", "scope", "snapshot", "native"]
)
def test_capture_wrong_scope_or_fault_cannot_read_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    worker, commands = case(tmp_path)
    prepared = prepare(worker)
    inspection = prepared.model_copy(
        update={
            "action": "inspect",
            "operation": prepared.operation.model_copy(
                update={"operation_id": "catalog"}
            ),
        }
    )
    if failure == "scope":
        inspection = inspection.model_copy(
            update={
                "operation": inspection.operation.model_copy(
                    update={"owner_id": "foreign"}
                )
            }
        )
    if failure == "snapshot":
        assert inspection.snapshot_ref is not None
        inspection = inspection.model_copy(
            update={
                "snapshot_ref": inspection.snapshot_ref.model_copy(
                    update={"sha256": "f" * 64}
                )
            }
        )
    capture = SiteCaptureRequest(
        inspection=inspection,
        collector_id="foreign" if failure == "collector" else "admin-product-catalog",
        collector_version="2" if failure == "version" else "1",
    )
    before = len(commands.calls)
    original = commands.run

    def broken(argv: tuple[str, ...], control: OperationControl) -> bytes:
        if PRODUCT_CATALOG_PHP in argv:
            commands.calls.append(argv)
            raise OSError("catalog failed")
        return original(argv, control)

    monkeypatch.setattr(commands, "run", broken)
    with pytest.raises((ValueError, OwnershipConflict, OSError)):
        worker.capture_task(capture, control=guard())
    assert len(commands.calls) == before + (failure == "native")
    assert worker.phase == ("quarantined" if failure == "native" else "prepared")
    if failure == "native":
        with pytest.raises(InvalidTransition):
            worker.capture_task(capture, control=guard())
